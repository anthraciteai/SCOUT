"""File-backed org vault: company employees, per-user SBIR work, cached council.

Layout (S3 keys and disk paths are the same):

  companies/{company_id}/mission.txt
  companies/{company_id}/products.md
  companies/{company_id}/employees.txt

  users/{user_id}/display_name.txt
  users/{user_id}/passwd
  users/{user_id}/me.md
  users/{user_id}/skills.txt
  users/{user_id}/sbir.txt
  users/{user_id}/companies.txt

  groups/{company_id}/{group_id}/members.txt
  groups/{company_id}/{group_id}/sbir.txt

  sbir/{topic_id}/{company_id}/shared/topic.json
  sbir/{topic_id}/{company_id}/shared/council.json
  sbir/{topic_id}/{company_id}/shared/proposal.md
  sbir/{topic_id}/{company_id}/shared/notes.md
  sbir/{topic_id}/{company_id}/users/{user_id}/flint.json
  sbir/{topic_id}/{company_id}/users/{user_id}/council.json
  sbir/{topic_id}/{company_id}/users/{user_id}/draft.md
  sbir/{topic_id}/{company_id}/users/{user_id}/notes.md
"""
from __future__ import annotations

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

    def write_json(self, key: str, obj: Any) -> None:
        self.write_text(key, json.dumps(obj, indent=2, default=str))

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

    # ---- org helpers -----------------------------------------------------

    def company_employees(self, company_id: str) -> list[str]:
        return self.lines(f"companies/{_ok(company_id)}/employees.txt")

    def in_company(self, ident: Identity, company_id: Optional[str] = None) -> bool:
        cid = _ok(company_id or ident.company_id)
        if ident.user_id in self.company_employees(cid):
            return True
        return cid in self.lines(f"users/{_ok(ident.user_id)}/companies.txt")

    def user_sbirs(self, user_id: str) -> list[str]:
        return self.lines(f"users/{_ok(user_id)}/sbir.txt")

    def group_sbirs(self, company_id: str, group_id: str) -> list[str]:
        return self.lines(f"groups/{_ok(company_id)}/{_ok(group_id)}/sbir.txt")

    def federated_sbirs(self, ident: Identity) -> list[str]:
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
        if not self.in_company(ident, cid):
            return False
        tid = _ok(topic_id)
        if tid in self.federated_sbirs(ident):
            return True
        # Employee of the company that owns this folder may open it (then we grant).
        return self.exists(f"sbir/{tid}/{_ok(cid)}/shared/topic.json") or self.in_company(ident, cid)

    def grant_sbir(self, ident: Identity, topic_id: str, meta: Optional[dict] = None) -> None:
        tid = _ok(topic_id)
        cid = _ok(ident.company_id)
        uid = _ok(ident.user_id)
        self.append_unique(f"users/{uid}/sbir.txt", tid)
        for g in ident.groups or ["capture"]:
            self.append_unique(f"groups/{cid}/{_ok(g)}/members.txt", uid)
            self.append_unique(f"groups/{cid}/{_ok(g)}/sbir.txt", tid)
        if meta:
            existing = self.read_json(f"sbir/{tid}/{cid}/shared/topic.json") or {}
            existing.update(meta)
            existing.setdefault("granted_by", uid)
            existing["updated_at"] = _now()
            self.write_json(f"sbir/{tid}/{cid}/shared/topic.json", existing)

    def user_path(self, topic_id: str, ident: Identity, name: str) -> str:
        return f"sbir/{_ok(topic_id)}/{_ok(ident.company_id)}/users/{_ok(ident.user_id)}/{name}"

    def shared_path(self, topic_id: str, ident: Identity, name: str) -> str:
        return f"sbir/{_ok(topic_id)}/{_ok(ident.company_id)}/shared/{name}"

    def cache_get(self, key: str, model: Optional[str] = None) -> Optional[Any]:
        obj = self.read_json(key)
        if not obj:
            return None
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
        self.write_json(key, body)
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
                    "sbirs": self.lines(f"users/{_ok(uid)}/sbir.txt"),
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
