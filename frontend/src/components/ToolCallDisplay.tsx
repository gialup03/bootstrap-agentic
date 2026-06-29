import { useState } from "react";
import { Message } from "../api";

interface Props {
  message: Message;
}

interface SearchResult {
  title: string;
  url: string;
  content: string;
}

interface SearchPayload {
  query?: string;
  results?: SearchResult[];
  error?: string;
}

const COLLAPSED_COUNT = 2;

function parseSearchPayload(content: string): SearchPayload | null {
  try {
    const parsed = JSON.parse(content);
    if (
      parsed &&
      typeof parsed === "object" &&
      (Array.isArray(parsed.results) || typeof parsed.error === "string")
    ) {
      return parsed as SearchPayload;
    }
  } catch {
    // Not JSON (e.g. calculator result) — fall back to plain text.
  }
  return null;
}

function SearchResults({ payload }: { payload: SearchPayload }) {
  const [expanded, setExpanded] = useState(false);
  const results = payload.results ?? [];
  const visible = expanded ? results : results.slice(0, COLLAPSED_COUNT);
  const hidden = results.length - visible.length;

  return (
    <div>
      {payload.query && (
        <div className="tool-query">Searched: “{payload.query}”</div>
      )}
      {payload.error && <div className="tool-error">{payload.error}</div>}
      {visible.map((r, i) => (
        <div key={i} className="search-result">
          <a href={r.url} target="_blank" rel="noopener noreferrer">
            {r.title || r.url}
          </a>
          <div className="search-result-url">{r.url}</div>
          <div className="search-result-snippet">{r.content}</div>
        </div>
      ))}
      {hidden > 0 && (
        <button className="tool-toggle" onClick={() => setExpanded(true)}>
          Show {hidden} more result{hidden > 1 ? "s" : ""}
        </button>
      )}
      {expanded && results.length > COLLAPSED_COUNT && (
        <button className="tool-toggle" onClick={() => setExpanded(false)}>
          Show less
        </button>
      )}
    </div>
  );
}

export default function ToolCallDisplay({ message }: Props) {
  const payload = parseSearchPayload(message.content);

  return (
    <div className="message tool">
      <div className="tool-label">Tool: {message.tool_name || "unknown"}</div>
      {payload ? (
        <SearchResults payload={payload} />
      ) : (
        <div style={{ whiteSpace: "pre-wrap" }}>{message.content}</div>
      )}
    </div>
  );
}
