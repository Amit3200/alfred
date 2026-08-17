import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { DocAuthImage } from "./DocAuthImage";

type Props = {
  content: string;
};

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
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
