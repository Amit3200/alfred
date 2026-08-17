import type { ReactNode } from "react";
import { isValidElement } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { DocAuthImage } from "./DocAuthImage";

type Props = {
  content: string;
};

function childText(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }
  if (Array.isArray(node)) {
    return node.map(childText).join("");
  }
  if (isValidElement<{ children?: ReactNode }>(node) && node.props.children != null) {
    return childText(node.props.children);
  }
  return "";
}

function toolResultClass(children: ReactNode): string | undefined {
  const text = childText(children).trim();
  if (text.startsWith("Failed")) {
    return "alfred-tool-result alfred-tool-result-fail";
  }
  if (text.startsWith("Succeeded")) {
    return "alfred-tool-result alfred-tool-result-ok";
  }
  return undefined;
}

export function ChatMarkdown({ content }: Props) {
  return (
    <div className="alfred-chat-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          img: ({ src, alt }) => <DocAuthImage src={src} alt={alt} />,
          li: ({ children }) => {
            const statusClass = toolResultClass(children);
            return <li className={statusClass}>{children}</li>;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
