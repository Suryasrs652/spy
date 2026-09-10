"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { apiGet, apiPost } from "@/lib/api";

interface Notification {
  id: string;
  type: string;
  title: string;
  body: string;
  link_path: string | null;
  read_at: string | null;
  created_at: string;
}

interface NotificationListResponse {
  notifications: Notification[];
  unread_count: number;
}

const POLL_INTERVAL_MS = 30000;

export function NotificationBell() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await apiGet<NotificationListResponse>("notifications?limit=10");
        if (!cancelled) {
          setNotifications(data.notifications);
          setUnreadCount(data.unread_count);
        }
      } catch {
        // The bell just keeps showing its last known state on failure.
      }
    }
    load();
    const interval = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  async function handleSelect(n: Notification) {
    setOpen(false);
    if (!n.read_at) {
      setUnreadCount((c) => Math.max(0, c - 1));
      setNotifications((prev) => prev.map((x) => (x.id === n.id ? { ...x, read_at: new Date().toISOString() } : x)));
      apiPost(`notifications/${n.id}/read`).catch(() => {});
    }
    if (n.link_path) router.push(n.link_path);
  }

  async function markAllRead() {
    const previousCount = unreadCount;
    setUnreadCount(0);
    setNotifications((prev) => prev.map((x) => ({ ...x, read_at: x.read_at ?? new Date().toISOString() })));
    try {
      await apiPost("notifications/read-all");
    } catch {
      setUnreadCount(previousCount);
    }
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-3 py-2 rounded-md text-sm hover:bg-white/5"
      >
        <span>Notifications</span>
        {unreadCount > 0 && (
          <span className="inline-flex items-center justify-center text-[10px] font-semibold rounded-full bg-accent text-white min-w-[18px] h-[18px] px-1">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute left-0 bottom-full mb-1 w-80 max-h-96 overflow-y-auto card p-2 z-50 shadow-lg">
          <div className="flex items-center justify-between px-2 py-1">
            <span className="text-xs uppercase tracking-wide text-muted">Notifications</span>
            {unreadCount > 0 && (
              <button onClick={markAllRead} className="text-xs text-accent hover:underline">
                Mark all read
              </button>
            )}
          </div>
          {notifications.length === 0 ? (
            <div className="px-2 py-6 text-center text-sm text-muted">No notifications yet.</div>
          ) : (
            notifications.map((n) => (
              <button
                key={n.id}
                onClick={() => handleSelect(n)}
                className="block w-full text-left px-2 py-2 rounded-md text-sm hover:bg-white/5"
              >
                <div className="font-medium flex items-center gap-2">
                  {!n.read_at && <span className="w-1.5 h-1.5 rounded-full bg-accent shrink-0" />}
                  <span>{n.title}</span>
                </div>
                <div className="text-xs text-muted mt-0.5 line-clamp-2">{n.body}</div>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
