import {
  DeleteOutlined,
  DownloadOutlined,
  PlusOutlined,
  SendOutlined,
} from "@ant-design/icons";
import { Button, Empty, Input, Spin, Typography } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import { AlfredMark } from "./AlfredMark";
import { ChatMessageContent } from "./ChatMessageContent";
import {
  api,
  ChatSessionDetail,
  ChatSessionSummary,
  getAdminToken,
} from "../api/client";
import { useApp } from "../context/AppContext";

const { Text } = Typography;
const { TextArea } = Input;

export function ChatPage() {
  const { notify, tokenInput } = useApp();
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [chat, setChat] = useState<ChatSessionDetail | null>(null);
  const [draft, setDraft] = useState("");
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [loadingChat, setLoadingChat] = useState(false);
  const [sending, setSending] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);

  const hasToken = Boolean((tokenInput || getAdminToken()).trim());

  const scrollToBottom = () => {
    requestAnimationFrame(() => {
      const el = threadRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
  };

  const loadSessions = useCallback(async () => {
    if (!hasToken) {
      setLoadingSessions(false);
      return;
    }
    setLoadingSessions(true);
    try {
      const data = await api.listChatSessions();
      setSessions(data.sessions);
      if (!activeId && data.sessions.length > 0) {
        setActiveId(data.sessions[0].id);
      }
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Failed to load chats");
    } finally {
      setLoadingSessions(false);
    }
  }, [activeId, hasToken, notify]);

  const loadChat = useCallback(
    async (id: string) => {
      if (!hasToken) return;
      setLoadingChat(true);
      try {
        const detail = await api.getChatSession(id);
        setChat(detail);
        scrollToBottom();
      } catch (err) {
        notify("error", err instanceof Error ? err.message : "Failed to load chat");
      } finally {
        setLoadingChat(false);
      }
    },
    [hasToken, notify],
  );

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    if (activeId) loadChat(activeId);
    else setChat(null);
  }, [activeId, loadChat]);

  const onNewChat = async () => {
    if (!hasToken) {
      notify("error", "Admin token required — paste it on the Secrets page.");
      return;
    }
    try {
      const created = await api.createChatSession();
      setSessions((prev) => [created, ...prev]);
      setActiveId(created.id);
      setChat({ ...created, messages: [] });
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Could not create chat");
    }
  };

  const onDeleteChat = async (id: string) => {
    try {
      await api.deleteChatSession(id);
      const remaining = sessions.filter((s) => s.id !== id);
      setSessions(remaining);
      if (activeId === id) {
        setActiveId(remaining[0]?.id ?? null);
      }
      notify("success", "Chat deleted.");
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Delete failed");
    }
  };

  const onSend = async () => {
    const text = draft.trim();
    if (!text || !activeId || sending) return;
    if (!hasToken) {
      notify("error", "Admin token required.");
      return;
    }
    setSending(true);
    setDraft("");
    setChat((prev) =>
      prev
        ? { ...prev, messages: [...prev.messages, { role: "user", content: text }] }
        : prev,
    );
    scrollToBottom();
    try {
      const result = await api.sendChatMessage(activeId, text);
      setChat(result.chat);
      setSessions((prev) => {
        const others = prev.filter((s) => s.id !== result.chat.id);
        return [
          {
            id: result.chat.id,
            title: result.chat.title,
            message_count: result.chat.message_count,
            updated_at: result.chat.updated_at,
            created_at: result.chat.created_at,
          },
          ...others,
        ];
      });
      if (result.export?.filename) {
        notify("success", `Exported ${result.export.filename}`);
      }
      scrollToBottom();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Send failed");
      setDraft(text);
    } finally {
      setSending(false);
    }
  };

  const onExport = async () => {
    if (!activeId) return;
    try {
      const result = await api.exportChatSession(activeId);
      const res = await fetch(api.chatExportDownloadUrl(result.filename), {
        headers: { "X-Alfred-Token": getAdminToken() },
      });
      if (!res.ok) throw new Error("Download failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = result.filename;
      a.click();
      URL.revokeObjectURL(url);
      notify("success", `Downloaded ${result.filename}`);
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Export failed");
    }
  };

  if (!hasToken) {
    return (
      <div className="alfred-chat-empty">
        <Empty description="Paste your admin token on the Secrets page to use Chat." />
      </div>
    );
  }

  return (
    <div className="alfred-chat-layout">
      <aside className="alfred-chat-sessions">
        <div className="alfred-chat-sessions-header">
          <Text strong>Chats</Text>
          <Button type="primary" size="small" icon={<PlusOutlined />} onClick={onNewChat}>
            New
          </Button>
        </div>
        {loadingSessions ? (
          <div className="alfred-chat-center">
            <Spin />
          </div>
        ) : sessions.length === 0 ? (
          <div className="alfred-chat-sessions-empty">
            <Text type="secondary">No chats yet</Text>
          </div>
        ) : (
          <ul className="alfred-chat-session-list">
            {sessions.map((session) => (
              <li key={session.id}>
                <button
                  type="button"
                  className={`alfred-chat-session-item${session.id === activeId ? " active" : ""}`}
                  onClick={() => setActiveId(session.id)}
                >
                  <span className="alfred-chat-session-title">{session.title}</span>
                  <span className="alfred-chat-session-meta">{session.message_count} msgs</span>
                </button>
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  aria-label="Delete chat"
                  onClick={() => onDeleteChat(session.id)}
                />
              </li>
            ))}
          </ul>
        )}
      </aside>

      <section className="alfred-chat-main">
        {!activeId ? (
          <div className="alfred-chat-welcome">
            <AlfredMark size={48} />
            <Typography.Title level={3}>Chat with Alfred</Typography.Title>
            <Text type="secondary">
              Each chat has its own memory — same capabilities as Slack (PRs, playbooks, git tools).
            </Text>
            <Button type="primary" icon={<PlusOutlined />} onClick={onNewChat}>
              Start a new chat
            </Button>
          </div>
        ) : (
          <>
            <header className="alfred-chat-header">
              <div>
                <Typography.Title level={4} style={{ margin: 0 }}>
                  {chat?.title || "Chat"}
                </Typography.Title>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  Separate memory · try &quot;export to markdown&quot; when done
                </Text>
              </div>
              <Button icon={<DownloadOutlined />} onClick={onExport} disabled={!chat?.messages.length}>
                Export MD
              </Button>
            </header>

            <div className="alfred-chat-thread" ref={threadRef}>
              {loadingChat ? (
                <div className="alfred-chat-center">
                  <Spin />
                </div>
              ) : chat?.messages.length ? (
                chat.messages.map((msg, index) => (
                  <div
                    key={`${index}-${msg.role}`}
                    className={`alfred-chat-bubble alfred-chat-bubble-${msg.role}`}
                  >
                    <div className="alfred-chat-bubble-label">
                      {msg.role === "user" ? "You" : "Alfred"}
                    </div>
                    <div className="alfred-chat-bubble-body">
                      {msg.role === "assistant" ? (
                        <ChatMessageContent content={msg.content} payload={msg.payload} />
                      ) : (
                        msg.content
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <div className="alfred-chat-welcome-inline">
                  <Text type="secondary">Ask Alfred anything — e.g. &quot;What are my open PRs?&quot;</Text>
                </div>
              )}
              {sending && (
                <div className="alfred-chat-bubble alfred-chat-bubble-assistant">
                  <div className="alfred-chat-bubble-label">Alfred</div>
                  <div className="alfred-chat-bubble-body">
                    <Spin size="small" /> Thinking…
                  </div>
                </div>
              )}
            </div>

            <footer className="alfred-chat-composer">
              <TextArea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Message Alfred… (Shift+Enter for newline)"
                autoSize={{ minRows: 1, maxRows: 6 }}
                onPressEnter={(e) => {
                  if (!e.shiftKey) {
                    e.preventDefault();
                    onSend();
                  }
                }}
                disabled={sending}
              />
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={onSend}
                loading={sending}
                disabled={!draft.trim()}
              >
                Send
              </Button>
            </footer>
          </>
        )}
      </section>
    </div>
  );
}
