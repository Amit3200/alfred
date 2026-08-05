import { Spin } from "antd";
import { useEffect, useState } from "react";
import { getAdminToken } from "../api/client";

type DocAuthImageProps = {
  src?: string;
  alt?: string;
};

export function DocAuthImage({ src, alt }: DocAuthImageProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!src || !src.startsWith("/api/repo-context/knowledge/")) {
      setBlobUrl(src || null);
      return;
    }

    let cancelled = false;
    let objectUrl: string | null = null;

    void (async () => {
      try {
        const res = await fetch(src, {
          headers: { "X-Alfred-Token": getAdminToken() },
        });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const blob = await res.blob();
        objectUrl = URL.createObjectURL(blob);
        if (!cancelled) {
          setBlobUrl(objectUrl);
          setFailed(false);
        }
      } catch {
        if (!cancelled) {
          setFailed(true);
          setBlobUrl(null);
        }
      }
    })();

    return () => {
      cancelled = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [src]);

  if (failed) {
    return (
      <div className="alfred-doc-image-fallback">
        {alt || "Image unavailable"}
      </div>
    );
  }

  if (!blobUrl) {
    return (
      <div className="alfred-doc-image-loading">
        <Spin size="small" /> Loading image…
      </div>
    );
  }

  return (
    <img
      src={blobUrl}
      alt={alt || "Documentation screenshot"}
      className="alfred-doc-image"
      loading="lazy"
    />
  );
}
