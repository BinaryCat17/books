import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";

import { api, ApiError } from "./api";
import { Admin } from "./pages/admin";
import { Library } from "./pages/library";
import { Login } from "./pages/login";
import { Viewer } from "./pages/viewer";
import type { User } from "./types";

export function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const nav = useNavigate();
  useEffect(() => {
    api.me().then(setUser, (e: ApiError) => setUser(e.status === 401 ? null : null));
  }, []);
  if (user === undefined) return <main className="muted">…</main>;
  if (user === null) return <Login onLogin={setUser} />;
  const logout = async () => {
    await api.logout();
    setUser(null);
    nav("/");
  };
  return (
    <>
      <nav className="top">
        <span className="brand">booksmith</span>
        <NavLink to="/" end>library</NavLink>
        {user.role === "admin" && <NavLink to="/admin">admin</NavLink>}
        <span className="spacer" />
        <span className="muted">{user.name} · {user.role}</span>
        <button onClick={logout}>log out</button>
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<Library user={user} />} />
          <Route path="/books/:root/:name/runs/:kind/:label" element={<Viewer user={user} />} />
          {user.role === "admin" && <Route path="/admin" element={<Admin />} />}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  );
}
