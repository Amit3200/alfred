import {
  CheckCircleOutlined,
  DeleteOutlined,
  DownloadOutlined,
  LoadingOutlined,
  PlusOutlined,
  StopOutlined,
} from "@ant-design/icons";
import { Button, Empty, Segmented, Spin, Typography } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import { AlfredMark } from "./AlfredMark";
import { ChatComposer } from "./ChatComposer";
import { ChatMessageBubble } from "./ChatMessageBubble";
import {
  api,
  ChatSessionDetail,
  ChatSessionSummary,
  ChatPersona,
  getAdminToken,
} from "../api/client";
import { useApp } from "../context/AppContext";

const { Text } = Typography;

const CHAT_PERSONA_STORAGE_KEY = "alfred_chat_persona";
const ACTIVE_CHAT_STORAGE_KEY = "alfred_active_chat_id";
const REPLY_POLL_MS = 1500;
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

function readStoredPersona(): ChatPersona {
  try {
    const value = sessionStorage.getItem(CHAT_PERSONA_STORAGE_KEY);
    if (value === "support" || value === "tech" || value === "all" || value === "general") {
      return value;
    }
    if (value === "qa") return "support";
    if (value === "debug") return "tech";
  } catch {
    // ignore
  }
  return "support";
}

function storePersona(persona: ChatPersona) {
  try {
    sessionStorage.setItem(CHAT_PERSONA_STORAGE_KEY, persona);
  } catch {
    // ignore
  }
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
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [loadingChat, setLoadingChat] = useState(false);
  const [sending, setSending] = useState(false);
  const [progressLabel, setProgressLabel] = useState<string | null>(null);
  const [progressSteps, setProgressSteps] = useState<
    Array<{ label: string; status: "done" | "active" | "error" }>
  >([]);
  const [progressPlan, setProgressPlan] = useState<{
    intent?: string;
    intent_label?: string;
    goal?: string;
    steps?: string[];
  } | null>(null);
  const [persona, setPersonaState] = useState<ChatPersona>(() => readStoredPersona());
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
      setProgressSteps([{ label: "Understanding your question", status: "active" }]);
      setProgressPlan(null);
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
              if (status.progress_steps?.length) {
                setProgressSteps(status.progress_steps);
              }
              if (status.progress_plan) {
                setProgressPlan(status.progress_plan);
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
        setProgressSteps([]);
        setProgressPlan(null);
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
    setProgressSteps([]);
    setProgressPlan(null);
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

  const setPersona = useCallback((value: ChatPersona) => {
    storePersona(value);
    setPersonaState(value);
  }, []);

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

  const onSend = async (text: string) => {
    if (!text || !activeId || sending) return;
    if (!hasToken) {
      notify("error", "Admin token required.");
      return;
    }
    const chatId = activeId;
    userStoppedPollRef.current.delete(chatId);
    setSending(true);
    try {
      const result = await api.sendChatMessage(chatId, text, persona);
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
                <div className="alfred-chat-persona-row">
                  <Text type="secondary" style={{ fontSize: 12, marginRight: 8 }}>
                    Mode
                  </Text>
                  <Segmented
                    size="small"
                    value={persona}
                    onChange={(value) => setPersona(value as ChatPersona)}
                    options={[
                      { label: "Support Q&A", value: "support", title: "Indexed docs handbook only" },
                      { label: "Tech Q&A", value: "tech", title: "Code repo, playbooks, runbooks" },
                      { label: "All", value: "all", title: "Full tool access" },
                      { label: "General", value: "general", title: "PR review and general skills" },
                    ]}
                  />
                </div>
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
                  <Spin />
                  <Text type="secondary" style={{ marginTop: 12 }}>
                    Loading messages…
                  </Text>
                </div>
              ) : visibleChat?.messages.length ? (
                visibleChat.messages.map((msg, index) => (
                  <ChatMessageBubble key={`${visibleChat.id}-${index}-${msg.role}`} message={msg} index={index} />
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
                    {progressPlan?.intent_label ? (
                      <div className="alfred-chat-progress-plan">
                        <div className="alfred-chat-progress-plan-title">
                          Plan · {progressPlan.intent_label}
                        </div>
                        {progressPlan.goal ? (
                          <div className="alfred-chat-progress-plan-goal">{progressPlan.goal}</div>
                        ) : null}
                        {progressPlan.steps?.length ? (
                          <div className="alfred-chat-progress-plan-steps">
                            {progressPlan.steps.join(" → ")}
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                    <ul className="alfred-chat-progress-timeline">
                      {(progressSteps.length > 0
                        ? progressSteps
                        : [{ label: (progressLabel || "Starting").replace(/…$/, ""), status: "active" as const }]
                      ).map((step, index) => (
                        <li
                          key={`${index}-${step.label}`}
                          className={`alfred-chat-progress-item alfred-chat-progress-item-${step.status}`}
                        >
                          <span className="alfred-chat-progress-icon" aria-hidden>
                            {step.status === "done" ? (
                              <CheckCircleOutlined />
                            ) : step.status === "error" ? (
                              <StopOutlined />
                            ) : (
                              <LoadingOutlined spin />
                            )}
                          </span>
                          <span>{step.label}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
            </div>

            <ChatComposer sending={sending} onSend={onSend} onStop={onStop} />
          </>
        )}
      </section>
    </div>
  );
}
