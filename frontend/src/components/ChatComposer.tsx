import { SendOutlined, StopOutlined } from "@ant-design/icons";
import { Button, Input } from "antd";
import { memo, useCallback, useState } from "react";

const { TextArea } = Input;

type ChatComposerProps = {
  sending: boolean;
  onSend: (text: string) => void | Promise<void>;
  onStop: () => void | Promise<void>;
};

export const ChatComposer = memo(function ChatComposer({
  sending,
  onSend,
  onStop,
}: ChatComposerProps) {
  const [draft, setDraft] = useState("");

  const handleSend = useCallback(() => {
    const text = draft.trim();
    if (!text || sending) return;
    setDraft("");
    void onSend(text);
  }, [draft, onSend, sending]);

  return (
    <footer className="alfred-chat-composer">
      <TextArea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder="Message Alfred… (Shift+Enter for newline)"
        autoSize={{ minRows: 1, maxRows: 6 }}
        onPressEnter={(e) => {
          if (!e.shiftKey) {
            e.preventDefault();
            handleSend();
          }
        }}
        disabled={sending}
      />
      {sending ? (
        <Button danger icon={<StopOutlined />} onClick={() => void onStop()}>
          Stop
        </Button>
      ) : (
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={handleSend}
          disabled={!draft.trim()}
        >
          Send
        </Button>
      )}
    </footer>
  );
});
