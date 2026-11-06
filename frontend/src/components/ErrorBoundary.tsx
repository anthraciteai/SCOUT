import { Component, type ReactNode } from "react";

type Props = {
  children: ReactNode;
  /** What failed, for the fallback copy (e.g. "Flint's take"). */
  label?: string;
  /** When this value changes, a previously-caught error is cleared so new
   *  (good) data can render — e.g. pass the result object or topic id. */
  resetKey?: unknown;
};

type State = { error: Error | null };

/**
 * Catches render crashes from a single agent card so one malformed local-model
 * response degrades to a readable notice instead of white-screening the app.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error) {
    // Surface for debugging without taking down the page.
    // eslint-disable-next-line no-console
    console.error("Agent render error:", this.props.label, error);
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="rounded-xl border border-red/40 bg-red/5 px-3.5 py-3 text-[13px] text-muted">
          <div className="mb-1 font-semibold text-red">
            Couldn’t render {this.props.label || "this result"}
          </div>
          <div className="leading-relaxed">
            The response came back in an unexpected shape — nothing else crashed. Re-run this voice
            to try again.
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
