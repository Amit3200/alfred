import {
  DeleteOutlined,
  DownloadOutlined,
  PlusOutlined,
  SendOutlined,
  StopOutlined,
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
const ACTIVE_CHAT_STORAGE_KEY = "alfred_active_chat_id";
const REPLY_POLL_MS = 2000;
const REPLY_POLL_MAX_MS = 15 * 60 * 1000;

function sleepInterruptible(ms: number, shouldStop: () => boolean) {
  return new Promise<void>((resolve) => {
    const started = Date.now();
    const tick = () => {
      if (shouldStop()) {
        resolve();
        return;
      }
      if (Date.now() - started >= ms) {
        resolve();
        return;
      }
      setTimeout(tick, Math.min(200, ms));
    };
    tick();
  });
}

function lastMessageIsUser(chat: ChatSessionDetail | null): boolean {
  const last = chat?.messages[chat.messages.length - 1];
  return last?.role === "user";
}

function readStoredActiveId(): string | null {
  try {
    return sessionStorage.getItem(ACTIVE_CHAT_STORAGE_KEY);
  } catch {
    return null;
  }
}

function storeActiveId(id: string | null) {
  try {
    if (id) sessionStorage.setItem(ACTIVE_CHAT_STORAGE_KEY, id);
    else sessionStorage.removeItem(ACTIVE_CHAT_STORAGE_KEY);
  } catch {
    // ignore storage failures
  }
}

function pickInitialSessionId(
  sessions: ChatSessionSummary[],
  current: string | null,
): string | null {
  if (current && sessions.some((session) => session.id === current)) {
    return current;
  }
  const stored = readStoredActiveId();
  if (stored && sessions.some((session) => session.id === stored)) {
    return stored;
  }
  return sessions[0]?.id ?? null;
}

export function ChatPage() {
  const { notify, tokenInput } = useApp();
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [activeId, setActiveIdState] = useState<string | null>(() => readStoredActiveId());
  const [chat, setChat] = useState<ChatSessionDetail | null>(null);
  const [draft, setDraft] = useState("");
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [loadingChat, setLoadingChat] = useState(false);
  const [sending, setSending] = useState(false);
  const [progressLabel, setProgressLabel] = useState<string | null>(null);
  const [recentTools, setRecentTools] = useState<string[]>([]);
  const threadRef = useRef<HTMLDivElement>(null);
  const activeIdRef = useRef<string | null>(activeId);
  const pollChatIdRef = useRef<string | null>(null);
  const pollAbortRef = useRef(false);
  const activeTaskIdRef = useRef<string | null>(null);
  const userStoppedPollRef = useRef<Set<string>>(new Set());

  const hasToken = Boolean((tokenInput || getAdminToken()).trim());

  const applyChatDetail = useCallback((detail: ChatSessionDetail) => {
    setChat(detail);
    setSessions((prev) => {
      const others = prev.filter((session) => session.id !== detail.id);
      return [
        {
          id: detail.id,
          title: detail.title,
          message_count: detail.message_count,
          updated_at: detail.updated_at,
          created_at: detail.created_at,
        },
        ...others,
      ];
    });
  }, []);

  const waitForAssistantReply = useCallback(
    async (chatId: string, taskId?: string) => {
      if (pollChatIdRef.current === chatId) {
        return;
      }
      pollChatIdRef.current = chatId;
      pollAbortRef.current = false;
      setSending(true);
      setProgressLabel("Thinking…");
      setRecentTools([]);
      let resolvedTaskId = taskId ?? activeTaskIdRef.current ?? undefined;
      if (!resolvedTaskId) {
        try {
          const active = await api.getChatActiveTask(chatId);
          resolvedTaskId = active.task_id ?? undefined;
        } catch {
          // keep polling session only
        }
      }
      if (resolvedTaskId) {
        activeTaskIdRef.current = resolvedTaskId;
      }
      const shouldStop = () =>
        pollAbortRef.current || activeIdRef.current !== chatId || userStoppedPollRef.current.has(chatId);
      const deadline = Date.now() + REPLY_POLL_MAX_MS;
      try {
        while (Date.now() < deadline) {
          if (shouldStop()) {
            return;
          }
          await sleepInterruptible(REPLY_POLL_MS, shouldStop);
          if (shouldStop()) {
            return;
          }
          if (resolvedTaskId) {
            try {
              const status = await api.getChatTaskStatus(resolvedTaskId);
              if (status.progress_label) {
                setProgressLabel(status.progress_label);
              }
              if (status.recent_tools) {
                setRecentTools(status.recent_tools);
              }
              if (status.status === "failed" || status.status === "cancelled") {
                break;
              }
            } catch {
              // task status may expire; keep polling session
            }
          }
          const detail = await api.getChatSession(chatId);
          if (shouldStop()) {
            return;
          }
          applyChatDetail(detail);
          const last = detail.messages[detail.messages.length - 1];
          if (last?.role === "assistant") {
            userStoppedPollRef.current.delete(chatId);
            scrollToBottom();
            return;
          }
        }
        if (!shouldStop()) {
          notify(
            "success",
            "Alfred is still working — keep this chat open; the reply will appear when ready.",
          );
        }
      } finally {
        if (pollChatIdRef.current === chatId) {
          pollChatIdRef.current = null;
        }
        if (!pollAbortRef.current) {
          activeTaskIdRef.current = null;
        }
        setSending(false);
        setProgressLabel(null);
        setRecentTools([]);
      }
    },
    [applyChatDetail, notify],
  );

  const onStop = useCallback(async () => {
    pollAbortRef.current = true;
    const chatId = activeIdRef.current;
    let taskId = activeTaskIdRef.current;
    if (chatId) {
      userStoppedPollRef.current.add(chatId);
    }
    setSending(false);
    setProgressLabel(null);
    setRecentTools([]);
    if (chatId && !taskId) {
      try {
        const active = await api.getChatActiveTask(chatId);
        taskId = active.task_id ?? null;
      } catch {
        // no active task metadata
      }
    }
    if (taskId) {
      try {
        await api.cancelChatTask(taskId);
      } catch (err) {
        notify("error", err instanceof Error ? err.message : "Could not stop task");
      }
    }
    if (chatId) {
      pollChatIdRef.current = null;
      activeTaskIdRef.current = null;
      for (let attempt = 0; attempt < 8; attempt += 1) {
        if (pollAbortRef.current && activeIdRef.current !== chatId) {
          break;
        }
        try {
          const detail = await api.getChatSession(chatId);
          if (activeIdRef.current === chatId) {
            applyChatDetail(detail);
          }
          const last = detail.messages[detail.messages.length - 1];
          if (last?.role === "assistant") {
            break;
          }
        } catch {
          // keep trying briefly for "Request stopped."
        }
        await sleepInterruptible(500, () => activeIdRef.current !== chatId);
      }
    }
  }, [applyChatDetail, notify]);

  const setActiveId = useCallback((id: string | null) => {
    activeIdRef.current = id;
    storeActiveId(id);
    setActiveIdState(id);
  }, []);

  useEffect(() => {
    activeIdRef.current = activeId;
  }, [activeId]);

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
      setActiveId(pickInitialSessionId(data.sessions, activeIdRef.current));
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Failed to load chats");
    } finally {
      setLoadingSessions(false);
    }
  }, [hasToken, notify, setActiveId]);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    if (!activeId || !hasToken) {
      setChat(null);
      setLoadingChat(false);
      return;
    }

    let cancelled = false;
    setLoadingChat(true);
    setChat(null);

    void (async () => {
      try {
        const detail = await api.getChatSession(activeId);
        if (cancelled || activeIdRef.current !== activeId) return;
        setChat(detail);
        scrollToBottom();
      } catch (err) {
        if (cancelled || activeIdRef.current !== activeId) return;
        notify("error", err instanceof Error ? err.message : "Failed to load chat");
        setChat(null);
      } finally {
        if (!cancelled && activeIdRef.current === activeId) {
          setLoadingChat(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [activeId, hasToken, notify]);

  const activeSession = sessions.find((session) => session.id === activeId) ?? null;
  const visibleChat = chat && chat.id === activeId ? chat : null;

  useEffect(() => {
    if (!visibleChat || loadingChat || sending || !hasToken) {
      return;
    }
    if (userStoppedPollRef.current.has(visibleChat.id)) {
      return;
    }
    if (lastMessageIsUser(visibleChat)) {
      void waitForAssistantReply(visibleChat.id);
    }
  }, [visibleChat, loadingChat, sending, hasToken, waitForAssistantReply]);

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
    const chatId = activeId;
    userStoppedPollRef.current.delete(chatId);
    setSending(true);
    setDraft("");
    try {
      const result = await api.sendChatMessage(chatId, text);
      if (activeIdRef.current !== chatId) return;
      applyChatDetail(result.chat);
      scrollToBottom();
      if (result.export?.filename) {
        notify("success", `Exported ${result.export.filename}`);
        return;
      }
      if (result.pending) {
        activeTaskIdRef.current = result.task_id ?? null;
        await waitForAssistantReply(chatId, result.task_id);
        return;
      }
      activeTaskIdRef.current = null;
      if (result.reply) {
        scrollToBottom();
      }
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Send failed");
      setDraft(text);
      if (activeIdRef.current === chatId) {
        try {
          const detail = await api.getChatSession(chatId);
          if (activeIdRef.current === chatId) {
            applyChatDetail(detail);
            if (lastMessageIsUser(detail)) {
              void waitForAssistantReply(chatId);
            }
          }
        } catch {
          // keep existing state if reload fails
        }
      }
    } finally {
      if (pollChatIdRef.current !== chatId) {
        setSending(false);
      }
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
                  {visibleChat?.title || activeSession?.title || "Chat"}
                </Typography.Title>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  Separate memory · say &quot;export to markdown&quot; or use Export MD to save
                </Text>
              </div>
              <Button
                icon={<DownloadOutlined />}
                onClick={onExport}
                disabled={!visibleChat?.messages.length}
              >
                Export MD
              </Button>
            </header>

            <div className="alfred-chat-thread" ref={threadRef}>
              {loadingChat ? (
                <div className="alfred-chat-center">
                  <Spin tip="Loading messages…" />
                </div>
              ) : visibleChat?.messages.length ? (
                visibleChat.messages.map((msg, index) => (
                  <div
                    key={`${index}-${msg.role}-${msg.content.slice(0, 24)}`}
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
                    <div className="alfred-chat-progress">
                      <Spin size="small" /> {progressLabel || "Thinking…"}
                    </div>
                    {recentTools.length > 0 && (
                      <div className="alfred-chat-progress-steps">
                        {recentTools.map((tool) => (
                          <span key={tool} className="alfred-chat-progress-step">
                            {tool.replace(/_/g, " ")}
                          </span>
                        ))}
                      </div>
                    )}
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
              {sending ? (
                <Button danger icon={<StopOutlined />} onClick={() => void onStop()}>
                  Stop
                </Button>
              ) : (
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  onClick={onSend}
                  disabled={!draft.trim()}
                >
                  Send
                </Button>
              )}
            </footer>
          </>
        )}
      </section>
    </div>
  );
}
