import { FormEvent, useState } from "react";

import { api, ApiError } from "../api";
import type { User } from "../types";

export function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      onLogin(await api.login(name, password));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  };
  return (
    <form className="login" onSubmit={submit}>
      <h1>booksmith</h1>
      <input id="login-name" placeholder="name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
      <input id="login-password" type="password" placeholder="password" value={password} onChange={(e) => setPassword(e.target.value)} />
      <button className="primary" type="submit">log in</button>
      {error && <div className="err">{error}</div>}
    </form>
  );
}
