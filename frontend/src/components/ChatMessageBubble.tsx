import { memo } from "react";
import { ChatMessageContent, type ResponsePayload } from "./ChatMessageContent";

type ChatMessage = {
  role: string;
  content: string;
  payload?: ResponsePayload | null;
};

type ChatMessageBubbleProps = {
  message: ChatMessage;
  index: number;
};

export const ChatMessageBubble = memo(function ChatMessageBubble({
  message,
  index,
}: ChatMessageBubbleProps) {
  return (
    <div className={`alfred-chat-bubble alfred-chat-bubble-${message.role}`}>
      <div className="alfred-chat-bubble-label">{message.role === "user" ? "You" : "Alfred"}</div>
      <div className="alfred-chat-bubble-body">
        {message.role === "assistant" ? (
          <ChatMessageContent content={message.content} payload={message.payload} />
        ) : (
          message.content
        )}
      </div>
    </div>
  );
}, (prev, next) =>
  prev.message.content === next.message.content &&
  prev.message.role === next.message.role &&
  prev.message.payload?.kind === next.message.payload?.kind &&
  prev.index === next.index);
