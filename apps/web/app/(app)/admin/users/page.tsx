"use client";

import { ROLE_LABELS } from "@intervue/config";
import { Search } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { RequireRole } from "@/components/layout/app-shell";
import { ErrorState, LoadingBlock, NativeSelect, PageHeader } from "@/components/shared/primitives";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/use-api";

interface AdminUser {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
  interviews: number;
}

export default function AdminUsersPage() {
  return (
    <RequireRole roles={["super_admin"]}>
      <Users />
    </RequireRole>
  );
}

function Users() {
  const [q, setQ] = useState("");
  const [dq, setDq] = useState("");
  const [role, setRole] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setDq(q), 300);
    return () => clearTimeout(t);
  }, [q]);
  const { data, error, loading, reload, setData } = useApi<{ total: number; items: AdminUser[] }>(`/admin/users?q=${encodeURIComponent(dq)}&role=${role}`);

  async function patch(u: AdminUser, body: Record<string, unknown>) {
    try {
      await api(`/admin/users/${u.id}`, { method: "PATCH", body });
      if (data) setData({ ...data, items: data.items.map((x) => (x.id === u.id ? { ...x, ...body } : x)) });
      toast.success("User updated");
    } catch (e) {
      toast.error(errorMessage(e));
    }
  }

  return (
    <>
      <PageHeader title="Users" description={data ? `${data.total} registered users (demo sessions excluded)` : undefined} />
      <div className="mb-4 flex gap-2">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
          <Input aria-label="Search users" placeholder="Search name or email" value={q} onChange={(e) => setQ(e.target.value)} className="h-9 pl-8" />
        </div>
        <NativeSelect aria-label="Filter by role" value={role} onChange={(e) => setRole(e.target.value)} className="max-w-48">
          <option value="">All roles</option>
          {Object.entries(ROLE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </NativeSelect>
      </div>
      {loading && !data ? (
        <LoadingBlock rows={5} />
      ) : error ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : (
        <div className="overflow-x-auto rounded-xl border bg-card">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr className="border-b">
                <th className="px-4 py-2.5 font-medium">User</th>
                <th className="px-4 py-2.5 font-medium">Role</th>
                <th className="px-4 py-2.5 font-medium">Interviews</th>
                <th className="px-4 py-2.5 font-medium">Joined</th>
                <th className="px-4 py-2.5 font-medium">Last login</th>
                <th className="px-4 py-2.5 font-medium">Active</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((u) => (
                <tr key={u.id} className="border-b last:border-0">
                  <td className="px-4 py-2.5">
                    <p className="font-medium">{u.full_name || "—"}</p>
                    <p className="text-xs text-muted-foreground">{u.email}</p>
                  </td>
                  <td className="px-4 py-2.5">
                    <NativeSelect aria-label={`Role for ${u.email}`} value={u.role} onChange={(e) => patch(u, { role: e.target.value })} className="h-8 max-w-48">
                      {Object.entries(ROLE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </NativeSelect>
                  </td>
                  <td className="px-4 py-2.5 tabular">{u.interviews}</td>
                  <td className="px-4 py-2.5 text-muted-foreground">{formatDate(u.created_at)}</td>
                  <td className="px-4 py-2.5 text-muted-foreground">{formatDate(u.last_login_at)}</td>
                  <td className="px-4 py-2.5">
                    <Switch aria-label={`${u.is_active ? "Disable" : "Enable"} ${u.email}`} checked={u.is_active} onCheckedChange={(v) => patch(u, { is_active: v })} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
