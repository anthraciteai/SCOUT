"""File-backed org vault. Existence of a named key is the gate; payloads live at sha.

Layout (S3 keys and disk paths are the same):

  companies/{company_id}/mission.txt
  companies/{company_id}/products.md
  companies/{company_id}/employees.txt          # derived roster (not the gate)
  companies/{company_id}/employees/{user_id}    # GATE: employed. delete = quit
  companies/{company_id}/tags.json

  users/{user_id}/display_name.txt
  users/{user_id}/passwd
  users/{user_id}/me.md                         # LLM resume blob
  users/{user_id}/skills.txt                    # roster excerpt (org desk)
  users/{user_id}/meta.json                     # {companies} — listing only
  users/{user_id}/companies/{company_id}        # reverse index; auth still needs employees/{you}
  users/{user_id}/sbir.txt                      # derived grant list
  users/{user_id}/sbir/{topic_id}               # GATE: this person was granted the topic
  users/{user_id}/resume/tags.json              # pointer {sha}
  users/{user_id}/resume/current.json           # pointer {sha}
  users/{user_id}/resume/v/{sha}/tags.json      # frozen matcher pack

  sbirs/{topic_id}/tags.json                    # GATE: this solicitation was tagged
  blobs/{sha}.json.gz                           # immutable council / agent runs

  groups/{company_id}/{group_id}/members.txt
  groups/{company_id}/{group_id}/sbir.txt
  groups/{company_id}/{group_id}/sbir/{topic_id}

  sbir/{topic_id}/{company_id}/shared/topic.json
  sbir/{topic_id}/{company_id}/shared/council.json          # pointer {sha}
  sbir/{topic_id}/{company_id}/shared/proposal.md
  sbir/{topic_id}/{company_id}/shared/notes.md
  sbir/{topic_id}/{company_id}/shared/approaches/{user_id}.json
  sbir/{topic_id}/{company_id}/shared/collab.json
  sbir/{topic_id}/{company_id}/users/{user_id}/meta.json    # desk flags + company_id
  sbir/{topic_id}/{company_id}/users/{user_id}/flint.json   # GATE: Flint ran (pointer)
  sbir/{topic_id}/{company_id}/users/{user_id}/council.json # GATE: council ran (pointer)
  sbir/{topic_id}/{company_id}/users/{user_id}/draft.md
  sbir/{topic_id}/{company_id}/users/{user_id}/draft.exists # GATE: non-empty private draft
  sbir/{topic_id}/{company_id}/users/{user_id}/notes.md
  sbir/{topic_id}/{company_id}/users/{user_id}/chat/{agent}.json
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
from datetime import datetime
from typing import Any, Optional

from .config import settings
from .identity import Identity

_SAFE = re.compile(r"^[A-Za-z0-9._:-]+$")


def _ok(part: str) -> str:
    p = (part or "").strip()
    if not p or not _SAFE.match(p) or p in (".", ".."):
        raise ValueError(f"unsafe path segment: {part!r}")
    return p


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


class Vault:
    def __init__(self, root: Optional[str] = None):
        self.root = root or settings.vault_dir
        os.makedirs(self.root, exist_ok=True)
        self._s3 = None
        if settings.storage_endpoint:
            try:
                self._s3 = _S3()
            except Exception:
                self._s3 = None

    def _disk(self, key: str) -> str:
        return os.path.join(self.root, key.replace("/", os.sep))

    def exists(self, key: str) -> bool:
        if os.path.isfile(self._disk(key)):
            return True
        if self._s3:
            return self._s3.exists(key)
        return False

    def read_bytes(self, key: str) -> Optional[bytes]:
        path = self._disk(key)
        if os.path.isfile(path):
            with open(path, "rb") as f:
                return f.read()
        if self._s3:
            data = self._s3.get(key)
            if data is not None:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as f:
                    f.write(data)
                return data
        return None

    def read_text(self, key: str) -> str:
        data = self.read_bytes(key)
        return data.decode("utf-8") if data else ""

    def write_bytes(self, key: str, data: bytes) -> None:
        path = self._disk(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        if self._s3:
            try:
                self._s3.put(key, data)
            except Exception:
                pass

    def write_text(self, key: str, text: str) -> None:
        self.write_bytes(key, (text or "").encode("utf-8"))

    def write_json(self, key: str, obj: Any, *, compact: bool = False) -> None:
        if compact:
            text = json.dumps(obj, separators=(",", ":"), ensure_ascii=False, default=str)
        else:
            text = json.dumps(obj, indent=2, default=str)
        self.write_text(key, text)

    def delete(self, key: str) -> None:
        path = self._disk(key)
        if os.path.isfile(path):
            os.remove(path)
        if self._s3:
            try:
                self._s3.delete(key)
            except Exception:
                pass

    def read_json(self, key: str) -> Optional[Any]:
        raw = self.read_text(key)
        if not raw.strip():
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def lines(self, key: str) -> list[str]:
        return [
            ln.strip()
            for ln in self.read_text(key).splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]

    def append_unique(self, key: str, item: str) -> None:
        rows = self.lines(key)
        if item not in rows:
            rows.append(item)
            self.write_text(key, "\n".join(rows) + "\n")

    def list_prefix(self, prefix: str) -> list[str]:
        base = self._disk(prefix.rstrip("/"))
        out: list[str] = []
        if os.path.isdir(base):
            for dirpath, _, files in os.walk(base):
                for name in files:
                    full = os.path.join(dirpath, name)
                    rel = os.path.relpath(full, self.root).replace(os.sep, "/")
                    out.append(rel)
        return sorted(out)

    # ---- existence gates -------------------------------------------------

    def employee_key(self, company_id: str, user_id: str) -> str:
        return f"companies/{_ok(company_id)}/employees/{_ok(user_id)}"

    def user_company_key(self, user_id: str, company_id: str) -> str:
        return f"users/{_ok(user_id)}/companies/{_ok(company_id)}"

    def user_meta_key(self, user_id: str) -> str:
        return f"users/{_ok(user_id)}/meta.json"

    def user_grant_key(self, user_id: str, topic_id: str) -> str:
        return f"users/{_ok(user_id)}/sbir/{_ok(topic_id)}"

    def group_grant_key(self, company_id: str, group_id: str, topic_id: str) -> str:
        return f"groups/{_ok(company_id)}/{_ok(group_id)}/sbir/{_ok(topic_id)}"

    def blob_key(self, sha: str) -> str:
        return f"blobs/{_ok(sha)}.json.gz"

    def work_meta_key(self, topic_id: str, company_id: str, user_id: str) -> str:
        return f"sbir/{_ok(topic_id)}/{_ok(company_id)}/users/{_ok(user_id)}/meta.json"

    def draft_gate_key(self, topic_id: str, company_id: str, user_id: str) -> str:
        return f"sbir/{_ok(topic_id)}/{_ok(company_id)}/users/{_ok(user_id)}/draft.exists"

    def hire(self, company_id: str, user_id: str, display_name: str = "") -> None:
        """Create the employment gate. Login never does this."""
        cid, uid = _ok(company_id), _ok(user_id)
        self.write_text(self.employee_key(cid, uid), (display_name or uid) + "\n")
        self.write_text(self.user_company_key(uid, cid), cid + "\n")
        self._rewrite_employees_txt(cid)
        self.refresh_user_meta(uid)

    def unhire(self, company_id: str, user_id: str) -> None:
        """Delete the employment gate. Reverse index and roster follow."""
        cid, uid = _ok(company_id), _ok(user_id)
        self.delete(self.employee_key(cid, uid))
        self.delete(self.user_company_key(uid, cid))
        self._rewrite_employees_txt(cid)
        self.refresh_user_meta(uid)

    def _rewrite_employees_txt(self, company_id: str) -> None:
        people = self.company_employees(company_id)
        self.write_text(
            f"companies/{_ok(company_id)}/employees.txt",
            ("\n".join(people) + "\n") if people else "",
        )

    def refresh_user_meta(self, user_id: str) -> dict[str, Any]:
        uid = _ok(user_id)
        companies = self.user_companies(uid)
        body = {
            "user_id": uid,
            "companies": companies,
            "company_id": companies[0] if companies else "",
            "updated_at": _now(),
        }
        self.write_json(self.user_meta_key(uid), body, compact=True)
        return body

    def company_employees(self, company_id: str) -> list[str]:
        """Roster from employees/{uid} files. employees.txt is not consulted."""
        prefix = f"companies/{_ok(company_id)}/employees/"
        found: list[str] = []
        for key in self.list_prefix(prefix):
            name = key[len(prefix) :].lstrip("/")
            if name and "/" not in name:
                found.append(name)
        return sorted(found)

    def user_companies(self, user_id: str) -> list[str]:
        """Orgs this person claims, intersected with the employment gate."""
        uid = _ok(user_id)
        prefix = f"users/{uid}/companies/"
        out: list[str] = []
        for key in self.list_prefix(prefix):
            cid = key[len(prefix) :].lstrip("/")
            if cid and "/" not in cid and self.exists(self.employee_key(cid, uid)):
                out.append(cid)
        return out

    def in_company(self, ident: Identity, company_id: Optional[str] = None) -> bool:
        cid = _ok(company_id or ident.company_id)
        return self.exists(self.employee_key(cid, ident.user_id))

    def user_sbirs(self, user_id: str) -> list[str]:
        uid = _ok(user_id)
        prefix = f"users/{uid}/sbir/"
        found: list[str] = []
        for key in self.list_prefix(prefix):
            name = key[len(prefix) :].lstrip("/")
            if name and "/" not in name:
                found.append(name)
        if found:
            return found
        return self.lines(f"users/{uid}/sbir.txt")

    def group_sbirs(self, company_id: str, group_id: str) -> list[str]:
        cid, gid = _ok(company_id), _ok(group_id)
        prefix = f"groups/{cid}/{gid}/sbir/"
        found: list[str] = []
        for key in self.list_prefix(prefix):
            name = key[len(prefix) :].lstrip("/")
            if name and "/" not in name:
                found.append(name)
        if found:
            return found
        return self.lines(f"groups/{cid}/{gid}/sbir.txt")

    def federated_sbirs(self, ident: Identity) -> list[str]:
        if not self.in_company(ident, ident.company_id):
            return []
        seen: list[str] = []
        for tid in self.user_sbirs(ident.user_id):
            if tid not in seen:
                seen.append(tid)
        cid = ident.company_id
        for g in ident.groups or ["capture"]:
            for tid in self.group_sbirs(cid, g):
                if tid not in seen:
                    seen.append(tid)
        return seen

    def can_read_sbir(self, ident: Identity, topic_id: str, company_id: Optional[str] = None) -> bool:
        cid = company_id or ident.company_id
        return self.in_company(ident, cid)

    def grant_sbir(self, ident: Identity, topic_id: str, meta: Optional[dict] = None) -> None:
        if not self.in_company(ident, ident.company_id):
            return
        tid = _ok(topic_id)
        cid = _ok(ident.company_id)
        uid = _ok(ident.user_id)
        self.write_text(self.user_grant_key(uid, tid), tid + "\n")
        self.append_unique(f"users/{uid}/sbir.txt", tid)
        for g in ident.groups or ["capture"]:
            gid = _ok(g)
            self.append_unique(f"groups/{cid}/{gid}/members.txt", uid)
            self.write_text(self.group_grant_key(cid, gid, tid), tid + "\n")
            self.append_unique(f"groups/{cid}/{gid}/sbir.txt", tid)
        if meta:
            existing = self.read_json(f"sbir/{tid}/{cid}/shared/topic.json") or {}
            existing.update(meta)
            existing.setdefault("granted_by", uid)
            existing["updated_at"] = _now()
            self.write_json(f"sbir/{tid}/{cid}/shared/topic.json", existing)
        self.refresh_work_meta(tid, cid, uid)

    def user_path(self, topic_id: str, ident: Identity, name: str) -> str:
        return f"sbir/{_ok(topic_id)}/{_ok(ident.company_id)}/users/{_ok(ident.user_id)}/{name}"

    def shared_path(self, topic_id: str, ident: Identity, name: str) -> str:
        return f"sbir/{_ok(topic_id)}/{_ok(ident.company_id)}/shared/{name}"

    def approach_key(self, topic_id: str, company_id: str, user_id: str) -> str:
        return (
            f"sbir/{_ok(topic_id)}/{_ok(company_id)}/shared/approaches/{_ok(user_id)}.json"
        )

    def collab_key(self, topic_id: str, company_id: str) -> str:
        return f"sbir/{_ok(topic_id)}/{_ok(company_id)}/shared/collab.json"

    def company_tags_key(self, company_id: str) -> str:
        return f"companies/{_ok(company_id)}/tags.json"

    def resume_tags_key(self, user_id: str, sha: Optional[str] = None) -> str:
        uid = _ok(user_id)
        if sha:
            return f"users/{uid}/resume/v/{_ok(sha)}/tags.json"
        return f"users/{uid}/resume/tags.json"

    def resume_current_key(self, user_id: str) -> str:
        return f"users/{_ok(user_id)}/resume/current.json"

    def topic_tags_key(self, topic_id: str) -> str:
        """sbirs/{sbir_id}/tags.json — one pack per solicitation id, not under a company bid."""
        return f"sbirs/{_ok(topic_id)}/tags.json"

    def chat_path(self, topic_id: str, ident: Identity, agent: str) -> str:
        return (
            f"sbir/{_ok(topic_id)}/{_ok(ident.company_id)}/users/{_ok(ident.user_id)}"
            f"/chat/{_ok(agent.lower())}.json"
        )

    def read_chat(self, topic_id: str, ident: Identity, agent: str) -> dict:
        obj = self.read_json(self.chat_path(topic_id, ident, agent))
        if isinstance(obj, dict) and isinstance(obj.get("messages"), list):
            return obj
        return {"agent": agent, "messages": []}

    def write_chat(self, topic_id: str, ident: Identity, agent: str, log: dict) -> dict:
        body = {
            "agent": agent,
            "updated_at": _now(),
            "messages": log.get("messages") or [],
        }
        if log.get("model"):
            body["model"] = log["model"]
        self.write_json(self.chat_path(topic_id, ident, agent), body)
        self.refresh_work_meta(topic_id, ident.company_id, ident.user_id)
        return body

    def list_chats(self, topic_id: str, ident: Identity) -> dict[str, int]:
        meta = self.read_json(self.work_meta_key(topic_id, ident.company_id, ident.user_id)) or {}
        chats = meta.get("chats")
        if isinstance(chats, dict):
            return {str(k): int(v) for k, v in chats.items()}
        prefix = (
            f"sbir/{_ok(topic_id)}/{_ok(ident.company_id)}/users/{_ok(ident.user_id)}/chat/"
        )
        out: dict[str, int] = {}
        for key in self.list_prefix(prefix):
            name = key.rsplit("/", 1)[-1]
            if name.endswith(".json"):
                out[name[: -len(".json")]] = 1
        return out

    def put_blob(self, obj: Any) -> str:
        raw = json.dumps(obj, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
        sha = hashlib.sha256(raw).hexdigest()[:16]
        key = self.blob_key(sha)
        if not self.exists(key):
            self.write_bytes(key, gzip.compress(raw, compresslevel=6))
        return sha

    def get_blob(self, sha: str) -> Optional[Any]:
        data = self.read_bytes(self.blob_key(sha))
        if not data:
            return None
        if data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)
        try:
            return json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def cache_get(self, key: str, model: Optional[str] = None) -> Optional[Any]:
        """Load a run. Missing slot file = never ran (do not invent a hit)."""
        if not self.exists(key):
            return None
        obj = self.read_json(key)
        if not obj:
            return None
        if obj.get("sha") and "result" not in obj:
            blob = self.get_blob(str(obj["sha"]))
            if not isinstance(blob, dict):
                return None
            obj = {**obj, **blob}
        if model and obj.get("model") and obj.get("model") != model:
            return None
        return obj

    def cache_put(self, key: str, payload: dict, model: str, kind: str) -> dict:
        body = {
            "kind": kind,
            "model": model,
            "cached_at": _now(),
            **payload,
        }
        sha = self.put_blob(body)
        pointer = {
            "sha": sha,
            "model": model,
            "kind": kind,
            "cached_at": body["cached_at"],
        }
        self.write_json(key, pointer, compact=True)
        parts = key.split("/")
        if len(parts) >= 5 and parts[0] == "sbir" and parts[3] == "users":
            self.refresh_work_meta(parts[1], parts[2], parts[4])
        elif len(parts) >= 5 and parts[0] == "sbir" and parts[3] == "shared":
            pass
        return {**pointer, **body}

    def set_draft_gate(self, topic_id: str, ident: Identity, text: str) -> None:
        key = self.draft_gate_key(topic_id, ident.company_id, ident.user_id)
        if (text or "").strip():
            self.write_text(key, "")
        else:
            self.delete(key)
        self.refresh_work_meta(topic_id, ident.company_id, ident.user_id)

    def refresh_work_meta(self, topic_id: str, company_id: str, user_id: str) -> dict[str, Any]:
        tid, cid, uid = _ok(topic_id), _ok(company_id), _ok(user_id)
        prefix = f"sbir/{tid}/{cid}/users/{uid}/"
        flint_key = prefix + "flint.json"
        council_key = prefix + "council.json"
        flint = self.read_json(flint_key) if self.exists(flint_key) else None
        council = self.read_json(council_key) if self.exists(council_key) else None
        chats: dict[str, int] = {}
        for key in self.list_prefix(prefix + "chat/"):
            name = key.rsplit("/", 1)[-1]
            if not name.endswith(".json"):
                continue
            log = self.read_json(key) or {}
            msgs = log.get("messages") if isinstance(log, dict) else None
            chats[name[: -len(".json")]] = len(msgs) if isinstance(msgs, list) else 1
        cached_at = ""
        for slot in (council, flint):
            if isinstance(slot, dict) and slot.get("cached_at"):
                cached_at = str(slot["cached_at"])
                break
        body = {
            "user_id": uid,
            "company_id": cid,
            "cached_at": cached_at,
            "has_draft": self.exists(self.draft_gate_key(tid, cid, uid)),
            "flint": self.exists(flint_key),
            "council": self.exists(council_key),
            "chat_turns": sum(chats.values()),
            "chats": chats,
            "updated_at": _now(),
        }
        self.write_json(self.work_meta_key(tid, cid, uid), body, compact=True)
        return body

    def bundle_resume(self, ident: Identity) -> str:
        uid = _ok(ident.user_id)
        cid = _ok(ident.company_id)
        parts: list[str] = []
        me = self.read_text(f"users/{uid}/me.md").strip()
        if me:
            parts.append(f"=== ME (this person — tools, jobs, stack) ===\n{me}")
        mission = self.read_text(f"companies/{cid}/mission.txt").strip()
        products = self.read_text(f"companies/{cid}/products.md").strip()
        company = "\n\n".join(p for p in (mission, products) if p)
        if company:
            parts.append(f"=== COMPANY / PRODUCTS ===\n{company}")
        mates: list[str] = []
        for other in self.company_employees(cid):
            if other == uid:
                continue
            skills = self.read_text(f"users/{_ok(other)}/skills.txt").strip()
            name = self.read_text(f"users/{_ok(other)}/display_name.txt").strip() or other
            if skills:
                mates.append(f"{name} ({other}): {skills}")
        if mates:
            parts.append(
                "=== TEAMMATES (same org — complementary skills for the proposal; "
                "do not pretend these are YOUR hands-on tools) ===\n" + "\n".join(mates)
            )
        return "\n\n".join(parts)

    def roster(self, company_id: str) -> list[dict]:
        cid = _ok(company_id)
        out = []
        for uid in self.company_employees(cid):
            out.append(
                {
                    "user_id": uid,
                    "display_name": self.read_text(f"users/{_ok(uid)}/display_name.txt").strip() or uid,
                    "skills": self.lines(f"users/{_ok(uid)}/skills.txt"),
                    "sbirs": self.user_sbirs(uid),
                }
            )
        return out


class _S3:
    def __init__(self):
        import boto3
        from botocore.config import Config
        from botocore.exceptions import ClientError

        self._ClientError = ClientError
        self.bucket = settings.storage_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint or None,
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "scout"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "scout-secret-key"),
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
            config=Config(s3={"addressing_style": "path"}),
        )
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            try:
                self.client.create_bucket(Bucket=self.bucket)
            except Exception:
                pass

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception:
            pass

    def get(self, key: str) -> Optional[bytes]:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=key)
            return obj["Body"].read()
        except Exception:
            return None

    def put(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)


_vault: Optional[Vault] = None


def get_vault() -> Vault:
    global _vault
    if _vault is None:
        _vault = Vault()
    return _vault
