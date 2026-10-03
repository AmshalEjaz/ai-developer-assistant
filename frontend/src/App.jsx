import {
  useEffect,
  useRef,
  useState,
} from "react";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import AuthPage from "./AuthPage";
import "./App.css";


const API_URL =
  "http://127.0.0.1:8000";

const MAX_ATTACHMENT_BYTES =
  2 * 1024 * 1024;

const ATTACHMENT_ACCEPT =
  ".py,.php,.js,.jsx,.ts,.tsx,.java,.cs,.sql,.json,.html,.css,.md,.txt,.xml,.yml,.yaml,.env.example";

const ACTIVE_CONVERSATION_STORAGE_KEY =
  "devpilot_active_conversation_id";


function formatUsageNumber(value) {
  if (
    value === null
    || value === undefined
  ) {
    return "—";
  }

  return Number(value).toLocaleString();
}


function formatResetTime(value) {
  if (!value) {
    return "—";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  return date.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}


function formatFileSize(value) {
  const bytes = Number(value || 0);

  if (bytes < 1024) {
    return `${bytes} B`;
  }

  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}


function apiErrorMessage(
  data,
  fallback = "Something went wrong."
) {
  if (
    typeof data?.detail
    === "string"
  ) {
    return data.detail;
  }

  if (
    typeof data?.detail?.message
    === "string"
  ) {
    return data.detail.message;
  }

  if (
    Array.isArray(data?.detail)
    && data.detail.length
  ) {
    return (
      data.detail[0]?.msg
      || fallback
    );
  }

  return fallback;
}


const CODE_LANGUAGE_LABELS = {
  bash: "Bash",
  c: "C",
  cpp: "C++",
  csharp: "C#",
  css: "CSS",
  html: "HTML",
  java: "Java",
  javascript: "JavaScript",
  js: "JavaScript",
  json: "JSON",
  jsx: "JSX",
  laravel: "Laravel",
  php: "PHP",
  powershell: "PowerShell",
  py: "Python",
  python: "Python",
  react: "React",
  shell: "Shell",
  sh: "Shell",
  sql: "SQL",
  ts: "TypeScript",
  tsx: "TSX",
  typescript: "TypeScript",
  xml: "XML",
};


function codeLanguageLabel(className = "") {
  const match = className.match(/language-([^\s]+)/i);

  if (!match) {
    return "Code";
  }

  const raw = match[1].toLowerCase();

  return (
    CODE_LANGUAGE_LABELS[raw]
    || raw.charAt(0).toUpperCase() + raw.slice(1)
  );
}


function CodeBlock({ children }) {
  const [copied, setCopied] = useState(false);

  const codeElement = Array.isArray(children)
    ? children[0]
    : children;

  const className =
    codeElement?.props?.className || "";

  const codeText = String(
    codeElement?.props?.children ?? ""
  ).replace(/\n$/, "");

  const language =
    codeLanguageLabel(className);

  const copyCode = async () => {
    try {
      await navigator.clipboard.writeText(codeText);
      setCopied(true);

      window.setTimeout(
        () => setCopied(false),
        1400
      );
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="code-block-shell">
      <div className="code-block-header">
        <span>{language}</span>

        <button
          type="button"
          className="code-copy-button"
          onClick={copyCode}
          aria-label={`Copy ${language} code`}
        >
          {copied ? "✓ Copied" : "⧉ Copy"}
        </button>
      </div>

      <pre>{children}</pre>
    </div>
  );
}


function UserMessageContent({ content }) {
  const [expanded, setExpanded] = useState(false);

  const text = String(content || "");
  const lineCount = text.split("\n").length;

  const isLong =
    text.length > 520
    || lineCount > 8;

  return (
    <div className="user-message-wrapper">
      <div
        className={
          `user-message-body ${isLong && !expanded
            ? "collapsed"
            : ""
          }`
        }
      >
        {text}
      </div>

      {isLong && (
        <button
          type="button"
          className="user-message-expand"
          onClick={() =>
            setExpanded((current) => !current)
          }
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      )}
    </div>
  );
}


function groupConversations(
  conversations
) {
  const groups = {
    TODAY: [],
    YESTERDAY: [],
    "PREVIOUS 7 DAYS": [],
    OLDER: [],
  };

  const now = new Date();

  const today = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate()
  );

  conversations.forEach(
    (conversation) => {

      const rawDate =
        conversation.updated_at
        || conversation.created_at;

      const parsed =
        new Date(rawDate);

      if (
        Number.isNaN(
          parsed.getTime()
        )
      ) {
        groups.OLDER.push(
          conversation
        );

        return;
      }

      const day = new Date(
        parsed.getFullYear(),
        parsed.getMonth(),
        parsed.getDate()
      );

      const difference =
        Math.round(
          (
            today.getTime()
            - day.getTime()
          )
          / 86400000
        );

      if (difference <= 0) {
        groups.TODAY.push(
          conversation
        );

      } else if (
        difference === 1
      ) {
        groups.YESTERDAY.push(
          conversation
        );

      } else if (
        difference <= 7
      ) {
        groups[
          "PREVIOUS 7 DAYS"
        ].push(
          conversation
        );

      } else {
        groups.OLDER.push(
          conversation
        );
      }
    }
  );

  return Object.entries(groups)
    .filter(
      ([, items]) =>
        items.length > 0
    );
}


function App() {

  const [message, setMessage] =
    useState("");

  const [messages, setMessages] =
    useState([]);

  const [
    conversations,
    setConversations,
  ] = useState([]);

  const [
    activeConversationId,
    setActiveConversationId,
  ] = useState(null);

  const [
    historyLoading,
    setHistoryLoading,
  ] = useState(false);

  const [
    historyError,
    setHistoryError,
  ] = useState("");

  const [
    conversationLoading,
    setConversationLoading,
  ] = useState(false);

  const [
    conversationRestorePending,
    setConversationRestorePending,
  ] = useState(true);

  const [
    activeAttachment,
    setActiveAttachment,
  ] = useState(null);

  const [
    pendingAttachmentFile,
    setPendingAttachmentFile,
  ] = useState(null);

  const [
    attachmentUploading,
    setAttachmentUploading,
  ] = useState(false);

  const [
    attachmentError,
    setAttachmentError,
  ] = useState("");

  const [
    isLoading,
    setIsLoading,
  ] = useState(false);

  const [
    sidebarOpen,
    setSidebarOpen,
  ] = useState(false);

  const [
    activePanel,
    setActivePanel,
  ] = useState(null);

  const [
    authUser,
    setAuthUser,
  ] = useState(null);

  const [
    authChecking,
    setAuthChecking,
  ] = useState(true);

  const [
    theme,
    setTheme,
  ] = useState(
    () =>
      localStorage.getItem(
        "devpilot_theme"
      ) === "dark"
        ? "dark"
        : "light"
  );

  const [
    settingsLoading,
    setSettingsLoading,
  ] = useState(false);

  const [
    settingsError,
    setSettingsError,
  ] = useState("");

  const [
    groqUsage,
    setGroqUsage,
  ] = useState(null);

  const [
    groqUsageLoading,
    setGroqUsageLoading,
  ] = useState(false);

  const [
    groqUsageError,
    setGroqUsageError,
  ] = useState("");

  const [
    memories,
    setMemories,
  ] = useState([]);

  const [
    memoryInput,
    setMemoryInput,
  ] = useState("");

  const [
    memoryLoading,
    setMemoryLoading,
  ] = useState(false);

  const [
    memorySaving,
    setMemorySaving,
  ] = useState(false);

  const [
    memoryError,
    setMemoryError,
  ] = useState("");

  const [
    memoryNotice,
    setMemoryNotice,
  ] = useState("");

  const [
    helpView,
    setHelpView,
  ] = useState("home");

  const [
    feedbackText,
    setFeedbackText,
  ] = useState("");

  const [
    feedbackSubmitting,
    setFeedbackSubmitting,
  ] = useState(false);

  const [
    feedbackStatus,
    setFeedbackStatus,
  ] = useState(null);

  const [
    conversationMenuId,
    setConversationMenuId,
  ] = useState(null);

  const [
    deleteTarget,
    setDeleteTarget,
  ] = useState(null);

  const [
    deletingConversationId,
    setDeletingConversationId,
  ] = useState(null);

  const [
    deleteError,
    setDeleteError,
  ] = useState("");

  const [
    renameTarget,
    setRenameTarget,
  ] = useState(null);

  const [
    renameTitle,
    setRenameTitle,
  ] = useState("");

  const [
    renamingConversation,
    setRenamingConversation,
  ] = useState(false);

  const [
    renameError,
    setRenameError,
  ] = useState("");

  const messagesEndRef =
    useRef(null);

  const pendingChatScrollRef =
    useRef(false);

  const composerTextareaRef =
    useRef(null);

  const fileInputRef =
    useRef(null);


  const suggestions = [
    {
      icon: "🐛",
      title: "Debug an error",
      text:
        "Help me understand this error",
    },
    {
      icon: "</>",
      title: "Review my code",
      text:
        "Analyze my code for problems",
    },
    {
      icon: "⚡",
      title: "Explain code",
      text:
        "Explain this code step by step",
    },
    {
      icon: "🗄",
      title: "Fix SQL",
      text:
        "Help me fix this SQL query",
    },
  ];


  const historyGroups =
    groupConversations(
      conversations
    );


  const activeConversation =
    conversations.find(
      (conversation) =>
        conversation.id
        === activeConversationId
    );


  function getToken() {
    return localStorage.getItem(
      "devpilot_token"
    );
  }


  function authHeaders(
    extra = {}
  ) {
    return {
      ...extra,

      Authorization:
        `Bearer ${getToken()}`,
    };
  }


  function resizeComposerTextarea(
    element
  ) {
    if (!element) {
      return;
    }

    const maxHeight = 220;

    element.style.height = "auto";

    const nextHeight = Math.min(
      element.scrollHeight,
      maxHeight
    );

    element.style.height =
      `${nextHeight}px`;

    element.style.overflowY =
      element.scrollHeight > maxHeight
        ? "auto"
        : "hidden";
  }


  function handleLogout() {

    localStorage.removeItem(
      "devpilot_token"
    );
    localStorage.removeItem(
      ACTIVE_CONVERSATION_STORAGE_KEY
    );

    setAuthUser(null);

    setConversations([]);
    setActiveConversationId(null);

    setMessages([]);
    setMessage("");
    setActiveAttachment(null);
    setPendingAttachmentFile(null);
    setAttachmentUploading(false);
    setAttachmentError("");

    setIsLoading(false);
    setConversationLoading(false);

    setActivePanel(null);
    setSidebarOpen(false);

    setConversationMenuId(null);
    setDeleteTarget(null);
    setDeletingConversationId(null);
    setDeleteError("");

    setRenameTarget(null);
    setRenameTitle("");
    setRenamingConversation(false);
    setRenameError("");

    setMemories([]);
    setMemoryInput("");
    setMemoryLoading(false);
    setMemorySaving(false);
    setMemoryError("");
    setMemoryNotice("");
  }


  function upsertMemory(
    memory
  ) {
    if (!memory) {
      return;
    }

    setMemories(
      (current) => {
        const remaining =
          current.filter(
            (item) =>
              item.id !== memory.id
              && !(
                memory.key !== "note"
                && item.key === memory.key
              )
          );

        return [
          memory,
          ...remaining,
        ];
      }
    );
  }


  function upsertConversation(
    conversation
  ) {
    setConversations(
      (current) => {

        const remaining =
          current.filter(
            (item) =>
              item.id
              !== conversation.id
          );

        return [
          conversation,
          ...remaining,
        ].sort(
          (a, b) =>
            new Date(
              b.updated_at
              || b.created_at
            )
            -
            new Date(
              a.updated_at
              || a.created_at
            )
        );
      }
    );
  }


  async function loadConversations() {

    const token = getToken();

    if (!token) {
      return;
    }

    setHistoryLoading(true);
    setHistoryError("");

    try {

      const response =
        await fetch(
          `${API_URL}/api/conversations`,
          {
            headers:
              authHeaders(),
          }
        );

      if (
        response.status === 401
      ) {
        handleLogout();
        return;
      }

      const data =
        await response.json();

      if (!response.ok) {
        throw new Error(
          apiErrorMessage(
            data,
            "Unable to load conversations."
          )
        );
      }

      const loadedConversations =
        data.conversations || [];

      setConversations(
        loadedConversations
      );

      return loadedConversations;

    } catch (error) {

      setHistoryError(
        error.message
        || "Unable to load conversations."
      );

      return [];

    } finally {

      setHistoryLoading(false);
    }
  }


  async function loadSettings() {

    const token = getToken();

    if (!token) {
      return;
    }

    setSettingsLoading(true);
    setSettingsError("");

    try {

      const response =
        await fetch(
          `${API_URL}/api/settings`,
          {
            headers:
              authHeaders(),
          }
        );

      if (
        response.status === 401
      ) {
        handleLogout();
        return;
      }

      const data =
        await response.json();

      if (!response.ok) {
        throw new Error(
          apiErrorMessage(
            data,
            "Unable to load settings."
          )
        );
      }

      const savedTheme =
        data.theme === "dark"
          ? "dark"
          : "light";

      setTheme(savedTheme);

    } catch (error) {

      setSettingsError(
        error.message
        || "Unable to load settings."
      );

    } finally {

      setSettingsLoading(false);
    }
  }


  async function loadGroqUsage() {

    const token = getToken();

    if (!token) {
      return;
    }

    setGroqUsageLoading(true);
    setGroqUsageError("");

    try {
      const response =
        await fetch(
          `${API_URL}/api/groq/usage`,
          {
            headers:
              authHeaders(),
          }
        );

      if (response.status === 401) {
        handleLogout();
        return;
      }

      const data =
        await response.json();

      if (!response.ok) {
        throw new Error(
          apiErrorMessage(
            data,
            "Unable to load Groq usage."
          )
        );
      }

      setGroqUsage(data);

    } catch (error) {
      setGroqUsageError(
        error.message
        || "Unable to load Groq usage."
      );

    } finally {
      setGroqUsageLoading(false);
    }
  }


  async function loadMemories() {

    const token = getToken();

    if (!token) {
      return;
    }

    setMemoryLoading(true);
    setMemoryError("");

    try {
      const response =
        await fetch(
          `${API_URL}/api/memories`,
          {
            headers:
              authHeaders(),
          }
        );

      if (response.status === 401) {
        handleLogout();
        return;
      }

      const data =
        await response.json();

      if (!response.ok) {
        throw new Error(
          apiErrorMessage(
            data,
            "Unable to load memories."
          )
        );
      }

      setMemories(
        data.memories || []
      );

    } catch (error) {
      setMemoryError(
        error.message
        || "Unable to load memories."
      );

    } finally {
      setMemoryLoading(false);
    }
  }


  async function addMemory(
    event
  ) {
    event?.preventDefault();

    const clean =
      memoryInput.trim();

    if (!clean || memorySaving) {
      return;
    }

    setMemorySaving(true);
    setMemoryError("");
    setMemoryNotice("");

    try {
      const response =
        await fetch(
          `${API_URL}/api/memories`,
          {
            method: "POST",
            headers:
              authHeaders({
                "Content-Type":
                  "application/json",
              }),
            body:
              JSON.stringify({
                memory: clean,
              }),
          }
        );

      if (response.status === 401) {
        handleLogout();
        return;
      }

      const data =
        await response.json();

      if (!response.ok) {
        throw new Error(
          apiErrorMessage(
            data,
            "Unable to save memory."
          )
        );
      }

      upsertMemory(data.memory);
      setMemoryInput("");
      setMemoryNotice(
        "Memory saved. DevPilot will use it in future chats."
      );

    } catch (error) {
      setMemoryError(
        error.message
        || "Unable to save memory."
      );

    } finally {
      setMemorySaving(false);
    }
  }


  async function deleteMemory(
    memoryId
  ) {
    setMemoryError("");
    setMemoryNotice("");

    try {
      const response =
        await fetch(
          `${API_URL}/api/memories/${memoryId}`,
          {
            method: "DELETE",
            headers:
              authHeaders(),
          }
        );

      if (response.status === 401) {
        handleLogout();
        return;
      }

      const data =
        await response.json();

      if (!response.ok) {
        throw new Error(
          apiErrorMessage(
            data,
            "Unable to delete memory."
          )
        );
      }

      setMemories(
        (current) =>
          current.filter(
            (item) =>
              item.id !== memoryId
          )
      );

      setMemoryNotice(
        "Memory removed."
      );

    } catch (error) {
      setMemoryError(
        error.message
        || "Unable to delete memory."
      );
    }
  }


  async function loadConversation(
    conversationId
  ) {

    setPendingAttachmentFile(null);
    setConversationLoading(true);

    setActivePanel(null);

    setSidebarOpen(false);

    try {

      const response =
        await fetch(
          `${API_URL}/api/conversations/${conversationId}`,
          {
            headers:
              authHeaders(),
          }
        );

      if (
        response.status === 401
      ) {
        handleLogout();
        return;
      }

      const data =
        await response.json();

      if (!response.ok) {
        throw new Error(
          apiErrorMessage(
            data,
            "Unable to load conversation."
          )
        );
      }

      setActiveConversationId(
        data.conversation.id
      );

      localStorage.setItem(
        ACTIVE_CONVERSATION_STORAGE_KEY,
        String(data.conversation.id)
      );

      upsertConversation(
        data.conversation
      );

      pendingChatScrollRef.current =
        true;

      setMessages(
        data.messages || []
      );

      setActiveAttachment(
        data.attachment || null
      );
      setAttachmentError("");

    } catch (error) {

      setMessages([
        {
          id:
            `conversation-error-${Date.now()}`,

          role:
            "assistant",

          error:
            true,

          content:
            error.message
            || "Unable to load conversation.",
        },
      ]);

    } finally {

      setConversationLoading(false);
    }
  }


  async function handleFileSelect(event) {
    const selectedFile =
      event.target.files?.[0];

    event.target.value = "";

    if (!selectedFile) {
      return;
    }

    if (selectedFile.size > MAX_ATTACHMENT_BYTES) {
      setAttachmentError(
        "File is too large. Maximum size is 2 MB."
      );
      return;
    }

    setAttachmentError("");
    setPendingAttachmentFile(
      selectedFile
    );
  }


  async function uploadPendingAttachment(
    conversationId
  ) {
    if (!pendingAttachmentFile) {
      return null;
    }

    setAttachmentUploading(true);
    setAttachmentError("");

    try {
      const formData = new FormData();
      formData.append(
        "file",
        pendingAttachmentFile
      );

      if (conversationId) {
        formData.append(
          "conversation_id",
          String(conversationId)
        );
      }

      const response = await fetch(
        `${API_URL}/api/files`,
        {
          method: "POST",
          headers: authHeaders(),
          body: formData,
        }
      );

      if (response.status === 401) {
        handleLogout();
        throw new Error(
          "Authentication required."
        );
      }

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          apiErrorMessage(
            data,
            "Unable to attach file."
          )
        );
      }

      setActiveConversationId(
        data.conversation.id
      );
      localStorage.setItem(
        ACTIVE_CONVERSATION_STORAGE_KEY,
        String(data.conversation.id)
      );
      upsertConversation(
        data.conversation
      );
      setActiveAttachment(
        data.attachment
      );

      return data;

    } finally {
      setAttachmentUploading(false);
    }
  }


  async function removeAttachment() {
    if (pendingAttachmentFile) {
      setPendingAttachmentFile(null);
      setAttachmentError("");
      return;
    }

    if (
      !activeConversationId
      || !activeAttachment
      || attachmentUploading
    ) {
      return;
    }

    setAttachmentUploading(true);
    setAttachmentError("");

    try {
      const response = await fetch(
        `${API_URL}/api/conversations/${activeConversationId}/file`,
        {
          method: "DELETE",
          headers: authHeaders(),
        }
      );

      if (response.status === 401) {
        handleLogout();
        return;
      }

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          apiErrorMessage(
            data,
            "Unable to remove file."
          )
        );
      }

      setActiveAttachment(null);

    } catch (error) {
      setAttachmentError(
        error.message
        || "Unable to remove file."
      );
    } finally {
      setAttachmentUploading(false);
    }
  }


  async function handleSend() {

    const userMessage =
      message.trim();

    if (
      !userMessage
      || isLoading
      || conversationLoading
      || attachmentUploading
    ) {
      return;
    }

    setIsLoading(true);
    setActivePanel(null);

    let conversationId =
      activeConversationId;
    let sentAttachment = null;

    try {
      if (pendingAttachmentFile) {
        const uploadResult =
          await uploadPendingAttachment(
            conversationId
          );

        conversationId =
          uploadResult.conversation.id;
        sentAttachment =
          uploadResult.attachment;

        setPendingAttachmentFile(null);
      }

      const optimisticId =
        `temp-${Date.now()}`;

      const optimisticMessage = {
        id:
          optimisticId,

        role:
          "user",

        content:
          userMessage,

        attachment: sentAttachment,
      };

      pendingChatScrollRef.current =
        true;

      setMessages(
        (current) => [
          ...current,
          optimisticMessage,
        ]
      );

      setMessage("");

      const body = {
        message:
          userMessage,
      };

      if (conversationId) {
        body.conversation_id =
          conversationId;
      }

      const response =
        await fetch(
          `${API_URL}/api/chat`,
          {
            method:
              "POST",

            headers:
              authHeaders({
                "Content-Type":
                  "application/json",
              }),

            body:
              JSON.stringify(body),
          }
        );

      if (
        response.status === 401
      ) {
        handleLogout();
        return;
      }

      const data =
        await response.json();

      if (!response.ok) {

        const failedConversation =
          data?.detail
            ?.conversation;

        if (
          failedConversation
        ) {
          setActiveConversationId(
            failedConversation.id
          );

          upsertConversation(
            failedConversation
          );
        }

        throw new Error(
          apiErrorMessage(
            data,
            "DevPilot could not answer right now."
          )
        );
      }

      setActiveConversationId(
        data.conversation.id
      );

      localStorage.setItem(
        ACTIVE_CONVERSATION_STORAGE_KEY,
        String(data.conversation.id)
      );

      upsertConversation(
        data.conversation
      );

      if (data.memory_saved) {
        upsertMemory(
          data.memory_saved
        );
      }

      if (
        Object.prototype.hasOwnProperty.call(
          data,
          "attachment"
        )
      ) {
        setActiveAttachment(
          data.attachment || null
        );
      }

      setMessages(
        (current) => {

          const withoutTemporary =
            current.filter(
              (item) =>
                item.id
                !== optimisticId
            );

          return [
            ...withoutTemporary,

            {
              ...data.user_message,
              attachment: sentAttachment,
            }
            || optimisticMessage,

            data.message,
          ];
        }
      );

    } catch (error) {

      setMessages(
        (current) => [
          ...current,

          {
            id:
              `error-${Date.now()}`,

            role:
              "assistant",

            error:
              true,

            content:
              error.message
              || (
                "I couldn't connect "
                + "to the DevPilot backend."
              ),
          },
        ]
      );

      loadConversations();

    } finally {

      setIsLoading(false);
      loadGroqUsage();
    }
  }


  function handleSuggestion(
    text
  ) {

    setMessage(text);

    setSidebarOpen(false);

    setActivePanel(null);
  }


  function handleNewChat() {

    localStorage.removeItem(
      ACTIVE_CONVERSATION_STORAGE_KEY
    );

    setActiveConversationId(
      null
    );

    setMessage("");
    setMessages([]);
    setActiveAttachment(null);
    setPendingAttachmentFile(null);
    setAttachmentUploading(false);
    setAttachmentError("");

    setIsLoading(false);
    setConversationLoading(false);

    setActivePanel(null);
    setSidebarOpen(false);
    setConversationMenuId(null);

    setRenameTarget(null);
    setRenameTitle("");
    setRenameError("");
  }


  function openDeleteConfirmation(
    conversation,
    event
  ) {
    event?.stopPropagation();

    setConversationMenuId(null);
    setDeleteError("");
    setDeleteTarget(conversation);
  }


  function openRenameChat(
    conversation,
    event
  ) {
    event?.stopPropagation();

    setConversationMenuId(null);
    setRenameTarget(conversation);
    setRenameTitle(
      conversation?.title || ""
    );
    setRenameError("");
  }


  function closeRenameChat() {
    if (renamingConversation) {
      return;
    }

    setRenameTarget(null);
    setRenameTitle("");
    setRenameError("");
  }


  async function handleRenameChat(
    event
  ) {
    event?.preventDefault();

    if (
      !renameTarget
      || renamingConversation
    ) {
      return;
    }

    const cleanTitle =
      renameTitle.trim();

    if (!cleanTitle) {
      setRenameError(
        "Chat title cannot be empty."
      );
      return;
    }

    setRenamingConversation(true);
    setRenameError("");

    try {
      const response = await fetch(
        `${API_URL}/api/conversations/${renameTarget.id}`,
        {
          method: "PATCH",
          headers:
            authHeaders({
              "Content-Type":
                "application/json",
            }),
          body:
            JSON.stringify({
              title: cleanTitle,
            }),
        }
      );

      if (response.status === 401) {
        handleLogout();
        return;
      }

      const data =
        await response.json();

      if (!response.ok) {
        throw new Error(
          apiErrorMessage(
            data,
            "Unable to rename chat."
          )
        );
      }

      upsertConversation(
        data.conversation
      );

      setRenameTarget(null);
      setRenameTitle("");
      setRenameError("");

    } catch (error) {
      setRenameError(
        error.message
        || "Unable to rename chat."
      );

    } finally {
      setRenamingConversation(false);
    }
  }


  async function deleteConversation() {
    if (
      !deleteTarget
      || deletingConversationId
    ) {
      return;
    }

    const conversationId =
      deleteTarget.id;

    setDeletingConversationId(
      conversationId
    );
    setDeleteError("");

    try {
      const response = await fetch(
        `${API_URL}/api/conversations/${conversationId}`,
        {
          method: "DELETE",
          headers: authHeaders(),
        }
      );

      if (response.status === 401) {
        handleLogout();
        return;
      }

      const data =
        await response.json();

      if (!response.ok) {
        throw new Error(
          apiErrorMessage(
            data,
            "Unable to delete chat."
          )
        );
      }

      setConversations(
        (current) =>
          current.filter(
            (conversation) =>
              conversation.id
              !== conversationId
          )
      );

      if (
        activeConversationId
        === conversationId
      ) {
        localStorage.removeItem(
          ACTIVE_CONVERSATION_STORAGE_KEY
        );
        setActiveConversationId(null);
        setMessages([]);
        setMessage("");
        setActiveAttachment(null);
        setPendingAttachmentFile(null);
        setAttachmentUploading(false);
        setAttachmentError("");
        setIsLoading(false);
        setConversationLoading(false);
        setActivePanel(null);
      }

      setDeleteTarget(null);

    } catch (error) {
      setDeleteError(
        error.message
        || "Unable to delete chat."
      );

    } finally {
      setDeletingConversationId(null);
    }
  }


  async function handleThemeChange(
    nextTheme
  ) {

    if (
      nextTheme === theme
      || settingsLoading
    ) {
      return;
    }

    setTheme(nextTheme);

    setSettingsError("");

    localStorage.setItem(
      "devpilot_theme",
      nextTheme
    );

    setSettingsLoading(true);

    try {

      const response =
        await fetch(
          `${API_URL}/api/settings/theme`,
          {
            method:
              "PUT",

            headers:
              authHeaders({
                "Content-Type":
                  "application/json",
              }),

            body:
              JSON.stringify({
                theme:
                  nextTheme,
              }),
          }
        );

      if (
        response.status === 401
      ) {
        handleLogout();
        return;
      }

      const data =
        await response.json();

      if (!response.ok) {
        throw new Error(
          apiErrorMessage(
            data,
            "Unable to save theme."
          )
        );
      }

    } catch (error) {

      setSettingsError(
        (
          "Theme changed for this "
          + "session, but it could "
          + "not be saved."
        )
      );

    } finally {

      setSettingsLoading(false);
    }
  }


  function togglePanel(
    panel
  ) {

    setActivePanel(
      (current) =>
        current === panel
          ? null
          : panel
    );

    if (
      panel === "help"
    ) {
      setHelpView("home");

      setFeedbackText("");

      setFeedbackStatus(null);
    }

    if (
      panel === "settings"
    ) {
      setSettingsError("");
      setMemoryError("");
      setMemoryNotice("");
      loadMemories();
      loadGroqUsage();
    }

    setSidebarOpen(false);
  }


  function openHelpView(
    view
  ) {

    setHelpView(view);

    setFeedbackText("");

    setFeedbackStatus(null);
  }


  async function submitFeedback(
    event
  ) {

    event.preventDefault();

    const clean =
      feedbackText.trim();

    if (!clean) {

      setFeedbackStatus({
        type: "error",

        message:
          "Please write a message first.",
      });

      return;
    }

    const type =
      helpView === "problem"
        ? "problem"
        : "feedback";

    setFeedbackSubmitting(true);

    setFeedbackStatus(null);

    try {

      const response =
        await fetch(
          `${API_URL}/api/feedback`,
          {
            method:
              "POST",

            headers:
              authHeaders({
                "Content-Type":
                  "application/json",
              }),

            body:
              JSON.stringify({
                type,
                message:
                  clean,
              }),
          }
        );

      if (
        response.status === 401
      ) {
        handleLogout();
        return;
      }

      const data =
        await response.json();

      if (!response.ok) {
        throw new Error(
          apiErrorMessage(
            data,
            "Unable to submit your message."
          )
        );
      }

      setFeedbackText("");

      setFeedbackStatus({
        type: "success",

        message:
          type === "problem"
            ? (
              "Problem report saved. "
              + "Thank you."
            )
            : (
              "Feedback saved. "
              + "Thank you."
            ),
      });

    } catch (error) {

      setFeedbackStatus({
        type:
          "error",

        message:
          error.message
          || (
            "Unable to submit "
            + "your message."
          ),
      });

    } finally {

      setFeedbackSubmitting(false);
    }
  }


  function renderHelpContent() {

    if (
      helpView === "getting-started"
    ) {
      return (
        <div className="help-subview">

          <button
            className="help-back"
            onClick={() =>
              openHelpView("home")
            }
          >
            ← Back
          </button>

          <div className="help-article">

            <h3>Getting started</h3>

            <p>
              DevPilot is your AI developer
              workspace. Ask a question,
              paste an error, or request
              help with code.
            </p>

            <ol>
              <li>
                Use New chat when
                you want a fresh topic.
              </li>

              <li>
                Your real chats
                automatically appear in
                the sidebar.
              </li>

              <li>
                Click an old conversation
                to continue where you
                stopped.
              </li>

              <li>
                Use Settings to switch
                between Light and Dark.
              </li>

              <li>
                Use the arrow beside your
                account to sign out.
              </li>
            </ol>

          </div>

        </div>
      );
    }


    if (
      helpView === "faq"
    ) {
      return (
        <div className="help-subview">

          <button
            className="help-back"
            onClick={() =>
              openHelpView("home")
            }
          >
            ← Back
          </button>

          <div className="help-article">

            <h3>Common questions</h3>

            <details>
              <summary>
                Are my conversations saved?
              </summary>

              <p>
                Yes. Conversations and
                messages are stored in
                your local SQLite database.
              </p>
            </details>

            <details>
              <summary>
                Can another user see my chats?
              </summary>

              <p>
                No. Conversation APIs are
                scoped to the logged-in
                account.
              </p>
            </details>

            <details>
              <summary>
                Does New chat delete
                old chats?
              </summary>

              <p>
                No. It only opens a fresh
                chat.
              </p>
            </details>

            <details>
              <summary>
                Is Dark mode remembered?
              </summary>

              <p>
                Yes. Your theme is saved
                for your account.
              </p>
            </details>

          </div>

        </div>
      );
    }


    if (
      helpView === "feedback"
      || helpView === "problem"
    ) {

      const isProblem =
        helpView === "problem";

      return (
        <div className="help-subview">

          <button
            className="help-back"
            onClick={() =>
              openHelpView("home")
            }
          >
            ← Back
          </button>

          <form
            className="feedback-form"
            onSubmit={
              submitFeedback
            }
          >

            <h3>
              {isProblem
                ? "Report a problem"
                : "Send feedback"}
            </h3>

            <p>
              {isProblem
                ? (
                  "Describe what went wrong "
                  + "and what you expected."
                )
                : (
                  "Tell us what you like or "
                  + "what could be improved."
                )}
            </p>

            <textarea
              value={
                feedbackText
              }
              onChange={
                (event) =>
                  setFeedbackText(
                    event.target.value
                  )
              }
              maxLength="5000"
              placeholder={
                isProblem
                  ? "Describe the problem..."
                  : "Write your feedback..."
              }
              rows="7"
            />

            {
              feedbackStatus && (
                <div
                  className={
                    `feedback-status ${feedbackStatus.type
                    }`
                  }
                >
                  {
                    feedbackStatus.message
                  }
                </div>
              )
            }

            <button
              className="feedback-submit"
              type="submit"
              disabled={
                feedbackSubmitting
              }
            >
              {feedbackSubmitting
                ? "Submitting..."
                : (
                  isProblem
                    ? "Submit report"
                    : "Send feedback"
                )}
            </button>

          </form>

        </div>
      );
    }


    return (
      <div className="help-grid">

        <button
          className="help-card"
          onClick={() =>
            openHelpView(
              "getting-started"
            )
          }
        >
          <span>📖</span>

          <div>
            <strong>
              Getting started
            </strong>

            <small>
              Learn how to use DevPilot.
            </small>
          </div>
        </button>

        <button
          className="help-card"
          onClick={() =>
            openHelpView(
              "feedback"
            )
          }
        >
          <span>💬</span>

          <div>
            <strong>
              Send feedback
            </strong>

            <small>
              Tell us what you think.
            </small>
          </div>
        </button>

        <button
          className="help-card"
          onClick={() =>
            openHelpView(
              "problem"
            )
          }
        >
          <span>🐛</span>

          <div>
            <strong>
              Report a problem
            </strong>

            <small>
              Let us know about an issue.
            </small>
          </div>
        </button>

        <button
          className="help-card"
          onClick={() =>
            openHelpView(
              "faq"
            )
          }
        >
          <span>❓</span>

          <div>
            <strong>
              Common questions
            </strong>

            <small>
              View frequently asked
              questions.
            </small>
          </div>
        </button>

      </div>
    );
  }


  // ==========================================================
  // EFFECTS
  // ==========================================================

  useEffect(
    () => {

      document
        .documentElement
        .setAttribute(
          "data-theme",
          theme
        );

      localStorage.setItem(
        "devpilot_theme",
        theme
      );

    },
    [theme]
  );


  useEffect(
    () => {
      resizeComposerTextarea(
        composerTextareaRef.current
      );
    },
    [message]
  );


  useEffect(
    () => {

      if (
        !pendingChatScrollRef.current
      ) {
        return;
      }

      pendingChatScrollRef.current =
        false;

      window.requestAnimationFrame(
        () => {
          messagesEndRef
            .current
            ?.scrollIntoView({
              behavior: "smooth",
              block: "end",
            });
        }
      );

    },
    [
      messages,
      isLoading,
    ]
  );


  useEffect(
    () => {

      const restoreLogin =
        async () => {

          const token =
            getToken();

          if (!token) {

            setAuthChecking(
              false
            );

            return;
          }

          try {

            const response =
              await fetch(
                `${API_URL}/api/auth/me`,
                {
                  headers:
                    authHeaders(),
                }
              );

            if (!response.ok) {
              throw new Error(
                "Session expired"
              );
            }

            const user =
              await response.json();

            setAuthUser(user);

          } catch {

            localStorage.removeItem(
              "devpilot_token"
            );

            setAuthUser(null);

          } finally {

            setAuthChecking(false);
          }
        };

      restoreLogin();

    },
    []
  );


  useEffect(
    () => {

      if (!authUser) {
        return;
      }

      loadSettings();
      loadMemories();
      loadGroqUsage();
      setConversationRestorePending(true);

      const restoreConversation =
        async () => {
          try {
            const loaded =
              (await loadConversations())
              || [];

            const storedId = Number(
              localStorage.getItem(
                ACTIVE_CONVERSATION_STORAGE_KEY
              )
            );

            if (
              storedId
              && loaded.some(
                (conversation) =>
                  conversation.id === storedId
              )
            ) {
              await loadConversation(
                storedId
              );
            } else if (storedId) {
              localStorage.removeItem(
                ACTIVE_CONVERSATION_STORAGE_KEY
              );
              setActiveConversationId(null);
            }
          } finally {
            setConversationRestorePending(false);
          }
        };

      restoreConversation();

    },
    [authUser]
  );


  // ==========================================================
  // AUTH GATE
  // ==========================================================

  if (authChecking) {

    return (
      <div className="auth-boot">
        Loading DevPilot...
      </div>
    );
  }


  if (!authUser) {

    return (
      <AuthPage
        onAuthenticated={
          setAuthUser
        }
      />
    );
  }


  if (conversationRestorePending) {

    return (
      <div className="auth-boot">
        Loading DevPilot...
      </div>
    );
  }


  // ==========================================================
  // RENDER
  // ==========================================================

  return (
    <div
      className="app"
      data-theme={theme}
    >

      {sidebarOpen && (
        <div
          className="sidebar-overlay"
          onClick={() =>
            setSidebarOpen(false)
          }
        />
      )}


      {renameTarget && (
        <div
          className="rename-modal-overlay"
          onMouseDown={(event) => {
            if (
              event.target
              === event.currentTarget
              && !renamingConversation
            ) {
              closeRenameChat();
            }
          }}
        >
          <form
            className="rename-modal"
            onSubmit={
              handleRenameChat
            }
            onMouseDown={(event) =>
              event.stopPropagation()
            }
            role="dialog"
            aria-modal="true"
            aria-labelledby="rename-chat-title"
          >
            <h3 id="rename-chat-title">
              Rename Chat
            </h3>

            <p>
              Enter a new name for
              this chat.
            </p>

            <input
              type="text"
              value={renameTitle}
              onChange={(event) =>
                setRenameTitle(
                  event.target.value
                )
              }
              maxLength={80}
              autoFocus
              disabled={
                renamingConversation
              }
              aria-label="Chat title"
            />

            {renameError && (
              <div className="rename-error">
                {renameError}
              </div>
            )}

            <div className="rename-modal-actions">
              <button
                type="button"
                className="rename-cancel"
                onClick={
                  closeRenameChat
                }
                disabled={
                  renamingConversation
                }
              >
                Cancel
              </button>

              <button
                type="submit"
                className="rename-save"
                disabled={
                  renamingConversation
                  || !renameTitle.trim()
                }
              >
                {
                  renamingConversation
                    ? "Saving..."
                    : "Save"
                }
              </button>
            </div>
          </form>
        </div>
      )}


      {deleteTarget && (
        <div
          className="delete-confirm-overlay"
          onMouseDown={(event) => {
            if (
              event.target
              === event.currentTarget
            ) {
              setDeleteTarget(null);
              setDeleteError("");
            }
          }}
        >
          <div
            className="delete-confirm-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-conversation-title"
          >
            <h3 id="delete-conversation-title">
              Delete Chat?
            </h3>

            <p>
              This will permanently remove
              this conversation and all of
              its messages.
            </p>

            <div className="delete-conversation-name">
              {deleteTarget.title}
            </div>

            {deleteError && (
              <div className="delete-error">
                {deleteError}
              </div>
            )}

            <div className="delete-confirm-actions">
              <button
                type="button"
                className="delete-cancel"
                disabled={
                  deletingConversationId
                  === deleteTarget.id
                }
                onClick={() => {
                  setDeleteTarget(null);
                  setDeleteError("");
                }}
              >
                Cancel
              </button>

              <button
                type="button"
                className="delete-confirm"
                disabled={
                  deletingConversationId
                  === deleteTarget.id
                }
                onClick={
                  deleteConversation
                }
              >
                {deletingConversationId
                  === deleteTarget.id
                  ? "Deleting..."
                  : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}


      <aside
        className={
          `sidebar ${sidebarOpen
            ? "open"
            : ""
          }`
        }
      >

        <div className="brand">

          <div className="brand-mark">
            ✦
          </div>

          <div>
            <h2>DevPilot</h2>

            <span>
              AI Developer Assistant
            </span>
          </div>

          <button
            className="sidebar-close"
            onClick={() =>
              setSidebarOpen(false)
            }
            aria-label="Close menu"
          >
            ×
          </button>

        </div>


        <button
          className="new-chat"
          onClick={
            handleNewChat
          }
        >
          <span>＋</span>
          New Chat
        </button>


        <div className="history">

          {historyLoading && (
            <div className="history-state">
              Loading conversations...
            </div>
          )}


          {!historyLoading
            && historyError && (
              <div className="history-state error">

                <span>
                  {historyError}
                </span>

                <button
                  onClick={
                    loadConversations
                  }
                >
                  Retry
                </button>

              </div>
            )}


          {!historyLoading
            && !historyError
            && conversations.length
            === 0 && (
              <div className="history-state">
                No conversations yet
              </div>
            )}


          {!historyLoading
            && !historyError
            && historyGroups.map(
              ([
                label,
                items,
              ]) => (

                <div
                  className="history-group"
                  key={label}
                >

                  <p>
                    {label}
                  </p>

                  {items.map(
                    (conversation) => (

                      <div
                        key={
                          conversation.id
                        }
                        className={
                          `history-entry ${activeConversationId
                            === conversation.id
                            ? "active"
                            : ""
                          }`
                        }
                      >

                        <button
                          className={
                            `history-item ${activeConversationId
                              === conversation.id
                              ? "active"
                              : ""
                            }`
                          }
                          onClick={() => {
                            setConversationMenuId(null);

                            loadConversation(
                              conversation.id
                            );
                          }}
                          title={
                            conversation.title
                          }
                        >

                          <span>
                            💬
                          </span>

                          <span className="history-item-label">
                            {
                              conversation.title
                            }
                          </span>

                        </button>

                        <button
                          className="conversation-menu-button"
                          type="button"
                          aria-label={
                            `Conversation options for ${conversation.title}`
                          }
                          onClick={(event) => {
                            event.stopPropagation();

                            setConversationMenuId(
                              (current) =>
                                current === conversation.id
                                  ? null
                                  : conversation.id
                            );
                          }}
                        >
                          •••
                        </button>

                        {conversationMenuId
                          === conversation.id && (
                            <div
                              className="conversation-menu"
                              onClick={(event) =>
                                event.stopPropagation()
                              }
                            >
                              <button
                                type="button"
                                className="conversation-delete-action"
                                onClick={(event) =>
                                  openDeleteConfirmation(
                                    conversation,
                                    event
                                  )
                                }
                              >
                                <svg
                                  xmlns="http://www.w3.org/2000/svg"
                                  viewBox="0 0 24 24"
                                  fill="currentColor"
                                >
                                  <path d="M3 6h18v2H3V6zm2 4h14v12a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V10zm3 2v8h2v-8H8zm4 0v8h2v-8h-2zM9 4V2h6v2h5v2H4V4h5z" />
                                </svg>

                                <span>Delete</span>
                              </button>
                              <button
                                type="button"
                                className="conversation-rename-action"
                                onClick={(event) =>
                                  openRenameChat(
                                    conversation,
                                    event
                                  )
                                }
                              >
                                <svg
                                  xmlns="http://www.w3.org/2000/svg"
                                  viewBox="0 0 24 24"
                                  fill="currentColor"
                                >
                                  <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1.003 1.003 0 0 0 0-1.42l-2.34-2.34a1.003 1.003 0 0 0-1.42 0l-1.83 1.83 3.75 3.75 1.84-1.82z" />
                                </svg>

                                <span>Rename</span>
                              </button>
                            </div>
                          )}

                      </div>
                    )
                  )}

                </div>
              )
            )}

        </div>


        <div className="sidebar-footer">

          <button
            className={
              activePanel
                === "settings"
                ? "footer-active"
                : ""
            }
            onClick={() =>
              togglePanel(
                "settings"
              )
            }
          >
            <span>⚙</span>
            Settings
          </button>


          <button
            className={
              activePanel
                === "help"
                ? "footer-active"
                : ""
            }
            onClick={() =>
              togglePanel(
                "help"
              )
            }
          >
            <span>?</span>
            Help & feedback
          </button>


          <div className="user">

            <div className="avatar">
              {
                authUser.username
                  ?.charAt(0)
                  .toUpperCase()
                || "U"
              }
            </div>

            <div className="user-info">
              <strong>
                {authUser.username}
              </strong>

              <small>
                {authUser.email}
              </small>
            </div>

            <button
              type="button"
              className="more"
              onClick={
                handleLogout
              }
              title="Sign out"
              aria-label="Sign out"
            >
              ↪
            </button>

          </div>

        </div>

      </aside>


      <main className="main">

        <header className="header">

          <div className="header-left">

            <button
              className="mobile-menu"
              onClick={() =>
                setSidebarOpen(true)
              }
              aria-label="Open menu"
            >
              ☰
            </button>

            <div>

              <h1>
                {
                  activeConversation
                    ?.title
                  || ""
                }
              </h1>

              <span>
                AI Developer Assistant
              </span>

            </div>

          </div>


          <div className="online">
            <span />
            AI Online
          </div>

        </header>


        {activePanel
          === "settings" && (

            <section className="info-panel">

              <div className="panel-header">

                <div>

                  <span className="panel-label">
                    PREFERENCES
                  </span>

                  <h2>Settings</h2>

                  <p>
                    Manage your DevPilot
                    workspace preferences.
                  </p>

                </div>

                <button
                  className="panel-close"
                  onClick={() =>
                    setActivePanel(null)
                  }
                >
                  ×
                </button>

              </div>


              <div className="settings-list">

                <div className="setting-row">

                  <div>
                    <strong>
                      Theme
                    </strong>

                    <span>
                      {
                        theme === "dark"
                          ? (
                            "Soft charcoal "
                            + "& blue"
                          )
                          : (
                            "Soft white "
                            + "& blue"
                          )
                      }
                    </span>
                  </div>


                  <div className="theme-toggle">

                    <button
                      className={
                        `theme-option ${theme
                          === "light"
                          ? "active"
                          : ""
                        }`
                      }
                      onClick={() =>
                        handleThemeChange(
                          "light"
                        )
                      }
                      disabled={
                        settingsLoading
                      }
                    >
                      ☀ Light
                    </button>

                    <button
                      className={
                        `theme-option ${theme
                          === "dark"
                          ? "active"
                          : ""
                        }`
                      }
                      onClick={() =>
                        handleThemeChange(
                          "dark"
                        )
                      }
                      disabled={
                        settingsLoading
                      }
                    >
                      ◐ Dark
                    </button>

                  </div>

                </div>


                {settingsError && (
                  <div className="settings-error">
                    {settingsError}
                  </div>
                )}


                <div className="setting-row">

                  <div>
                    <strong>
                      AI Assistant
                    </strong>

                    <span>
                      Developer mode
                    </span>
                  </div>

                  <span className="status-badge">
                    Active
                  </span>

                </div>


                <div className="setting-row">

                  <div>
                    <strong>
                      Workspace
                    </strong>

                    <span>
                      Local SQLite workspace
                    </span>
                  </div>

                  <span className="setting-value">
                    Local
                  </span>

                </div>


                <div className="groq-usage-card">

                  <div className="groq-usage-header">
                    <div>
                      <strong>Groq API Usage</strong>
                      <span>Latest rate-limit snapshot from Groq</span>
                    </div>

                    <button
                      type="button"
                      className="groq-refresh"
                      onClick={loadGroqUsage}
                      disabled={groqUsageLoading}
                    >
                      {groqUsageLoading
                        ? "Refreshing..."
                        : "Refresh"}
                    </button>
                  </div>

                  {groqUsageError ? (
                    <div className="groq-usage-message error">
                      {groqUsageError}
                    </div>
                  ) : !groqUsage?.available ? (
                    <div className="groq-usage-message">
                      {groqUsageLoading
                        ? "Loading usage..."
                        : (
                          groqUsage?.message
                          || "Usage available after the first AI response."
                        )}
                    </div>
                  ) : (
                    <>
                      <div className="groq-usage-meta">
                        <span>
                          Model: {groqUsage.model || "—"}
                        </span>

                        <span
                          className={
                            `groq-status ${groqUsage.status
                              === "rate_limited"
                              ? "limited"
                              : "available"
                            }`
                          }
                        >
                          {groqUsage.status === "rate_limited"
                            ? "Rate limited"
                            : "Available"}
                        </span>
                      </div>

                      <div className="groq-usage-grid">
                        <div className="groq-metric">
                          <span>Daily requests</span>
                          <strong>
                            {formatUsageNumber(
                              groqUsage.requests?.used
                            )}
                            {" / "}
                            {formatUsageNumber(
                              groqUsage.requests?.limit
                            )}
                            {" used"}
                          </strong>
                          <small>
                            {formatUsageNumber(
                              groqUsage.requests?.remaining
                            )}
                            {" remaining · Reset "}
                            {formatResetTime(
                              groqUsage.requests?.reset_at
                            )}
                          </small>
                        </div>

                        <div className="groq-metric">
                          <span>Tokens / minute</span>
                          <strong>
                            {formatUsageNumber(
                              groqUsage.tokens?.used
                            )}
                            {" / "}
                            {formatUsageNumber(
                              groqUsage.tokens?.limit
                            )}
                            {" used"}
                          </strong>
                          <small>
                            {formatUsageNumber(
                              groqUsage.tokens?.remaining
                            )}
                            {" remaining · Reset "}
                            {formatResetTime(
                              groqUsage.tokens?.reset_at
                            )}
                          </small>
                        </div>
                      </div>

                      {groqUsage.retry_after_seconds != null && (
                        <div className="groq-retry">
                          Retry after {groqUsage.retry_after_seconds}s
                        </div>
                      )}
                    </>
                  )}

                </div>


                <div className="memory-section">

                  <div className="memory-section-header">
                    <div>
                      <strong>Saved memories</strong>
                      <span>
                        Explicit preferences and context DevPilot can reuse in future conversations.
                      </span>
                    </div>

                    <span className="memory-count">
                      {memories.length}/50
                    </span>
                  </div>


                  <form
                    className="memory-add-form"
                    onSubmit={addMemory}
                  >
                    <input
                      type="text"
                      value={memoryInput}
                      onChange={(event) =>
                        setMemoryInput(
                          event.target.value
                        )
                      }
                      maxLength="2000"
                      placeholder="e.g. Always reply to me in Roman Urdu"
                    />

                    <button
                      type="submit"
                      disabled={
                        memorySaving
                        || !memoryInput.trim()
                      }
                    >
                      {memorySaving
                        ? "Saving..."
                        : "Add memory"}
                    </button>
                  </form>


                  <p className="memory-hint">
                    You can also say “remember this”, “add to memory”, or “yaad rakhna” in chat. DevPilot does not silently save preferences.
                  </p>


                  {memoryError && (
                    <div className="memory-status error">
                      {memoryError}
                    </div>
                  )}

                  {memoryNotice && (
                    <div className="memory-status success">
                      {memoryNotice}
                    </div>
                  )}


                  <div className="memory-list">
                    {memoryLoading ? (
                      <div className="memory-empty">
                        Loading memories...
                      </div>
                    ) : memories.length === 0 ? (
                      <div className="memory-empty">
                        No saved memories yet.
                      </div>
                    ) : (
                      memories.map(
                        (memory) => (
                          <div
                            className="memory-item"
                            key={memory.id}
                          >
                            <div>
                              <small>
                                {memory.key === "preferred_language"
                                  ? "Language preference"
                                  : "Memory"}
                              </small>

                              <p>
                                {memory.value}
                              </p>
                            </div>

                            <button
                              type="button"
                              onClick={() =>
                                deleteMemory(
                                  memory.id
                                )
                              }
                              title="Delete memory"
                              aria-label="Delete memory"
                            >
                              ×
                            </button>
                          </div>
                        )
                      )
                    )}
                  </div>

                </div>

              </div>

            </section>
          )}


        {activePanel
          === "help" && (

            <section className="info-panel">

              <div className="panel-header">

                <div>

                  <span className="panel-label">
                    SUPPORT
                  </span>

                  <h2>
                    Help & feedback
                  </h2>

                  <p>
                    Get help with DevPilot
                    or share your feedback.
                  </p>

                </div>

                <button
                  className="panel-close"
                  onClick={() =>
                    setActivePanel(null)
                  }
                >
                  ×
                </button>

              </div>

              {renderHelpContent()}

            </section>
          )}


        {!activePanel
          && (
            conversationLoading
            || messages.length > 0
          ) && (

            <section className="chat-area">

              {conversationLoading ? (

                <div className="chat-loading">
                  Loading conversation...
                </div>

              ) : (
                <>
                  {messages.map(
                    (item) => (

                      <div
                        key={item.id}
                        className={
                          `chat-message ${item.role
                            === "user"
                            ? "user-message"
                            : "assistant-message"
                          }`
                        }
                      >

                        <div className="message-avatar">

                          {item.role
                            === "user"
                            ? (
                              authUser.username
                                ?.charAt(0)
                                .toUpperCase()
                              || "U"
                            )
                            : "✦"
                          }

                        </div>


                        <div className="message-content">

                          <div className="message-name">

                            {item.role
                              === "user"
                              ? "You"
                              : "DevPilot"}

                          </div>


                          <div
                            className={
                              `message-text ${item.error
                                ? "error"
                                : ""
                              }`
                            }
                          >
                            {item.role
                              === "user" ? (
                              <UserMessageContent
                                content={item.content}
                              />
                            ) : (
                              <ReactMarkdown
                                remarkPlugins={[
                                  remarkGfm
                                ]}
                                components={{
                                  pre: CodeBlock
                                }}
                              >
                                {item.content}
                              </ReactMarkdown>
                            )}

                          </div>

                          {item.role === "user"
                            && item.attachment && (
                            <div className="message-attachment">
                              <div className="attachment-chip-icon">
                                &lt;/&gt;
                              </div>
                              <div className="attachment-chip-copy">
                                <strong>
                                  {item.attachment.filename}
                                </strong>
                                <span>
                                  {formatFileSize(
                                    item.attachment.size_bytes
                                  )}
                                </span>
                              </div>
                            </div>
                          )}

                        </div>

                      </div>
                    )
                  )}


                  {isLoading && (

                    <div className="chat-message assistant-message">

                      <div className="message-avatar">
                        ✦
                      </div>

                      <div className="message-content">

                        <div className="message-name">
                          DevPilot
                        </div>

                        <div className="message-text typing">
                          <span />
                          <span />
                          <span />
                        </div>

                      </div>

                    </div>
                  )}

                </>
              )}

              <div
                ref={
                  messagesEndRef
                }
              />

            </section>
          )}


        {!activePanel
          && !conversationLoading
          && messages.length === 0
          && (

            <section className="workspace">

              <div className="welcome">

                <div className="welcome-symbol">
                  <span>✦</span>
                </div>

                <div className="eyebrow">
                  YOUR DEVELOPER WORKSPACE
                </div>

                <h2>
                  What are you
                  <span>
                    {" "}building today?
                  </span>
                </h2>

                <p>
                  Ask questions, debug errors,
                  review code, or get help
                  with your next development
                  task.
                </p>

              </div>


              <div className="suggestions">

                {suggestions.map(
                  (item, index) => (

                    <button
                      className="suggestion"
                      key={index}
                      onClick={() =>
                        handleSuggestion(
                          item.text
                        )
                      }
                    >

                      <div className="suggestion-icon">
                        {item.icon}
                      </div>

                      <div className="suggestion-content">

                        <strong>
                          {item.title}
                        </strong>

                        <span>
                          {item.text}
                        </span>

                      </div>

                      <span className="arrow">
                        ↗
                      </span>

                    </button>
                  )
                )}

              </div>

            </section>
          )}


        {!activePanel && (

          <div className="composer-wrapper">

            {pendingAttachmentFile && (
              <div className="attachment-chip">
                <div className="attachment-chip-icon">
                  &lt;/&gt;
                </div>

                <div className="attachment-chip-copy">
                  <strong>
                    {pendingAttachmentFile.name}
                  </strong>
                  <span>
                    {formatFileSize(
                      pendingAttachmentFile.size
                    )}
                  </span>
                </div>

                <button
                  type="button"
                  className="attachment-remove"
                  onClick={removeAttachment}
                  disabled={attachmentUploading}
                  aria-label="Remove attached file"
                >
                  ×
                </button>
              </div>
            )}

            {attachmentError && (
              <div className="attachment-error">
                {attachmentError}
              </div>
            )}

            <div className="composer">

              <input
                ref={fileInputRef}
                className="attachment-input"
                type="file"
                accept={ATTACHMENT_ACCEPT}
                onChange={handleFileSelect}
              />

              <button
                type="button"
                className="attach"
                aria-label="Attach developer file"
                title="Attach one code/text file (max 2 MB)"
                disabled={
                  attachmentUploading
                  || isLoading
                  || conversationLoading
                }
                onClick={() =>
                  fileInputRef.current?.click()
                }
              >
                {attachmentUploading
                  ? "…"
                  : "＋"}
              </button>


              <textarea
                ref={
                  composerTextareaRef
                }
                value={message}
                onChange={
                  (event) => {
                    setMessage(
                      event.target.value
                    );

                    resizeComposerTextarea(
                      event.target
                    );
                  }
                }
                placeholder={
                  "Ask anything about "
                  + "your code..."
                }
                rows="1"
                disabled={
                  isLoading
                  || conversationLoading
                }
                onKeyDown={
                  (event) => {

                    if (
                      event.key
                      === "Enter"
                      && !event.shiftKey
                    ) {
                      event.preventDefault();

                      handleSend();
                    }
                  }
                }
              />


              <button
                className="send"
                onClick={
                  handleSend
                }
                disabled={
                  !message.trim()
                  || isLoading
                  || conversationLoading
                }
                aria-label="Send message"
              >
                {isLoading
                  ? "..."
                  : "↑"}
              </button>

            </div>


            <div className="composer-footer">

              <span>
                AI can make mistakes.
                Review important code
                before using it.
              </span>

            </div>

          </div>
        )}

      </main>

    </div>
  );
}


export default App;