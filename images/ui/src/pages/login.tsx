import { FormEvent, useState } from "react";

import { api, errorText } from "../api";
import type { User } from "../types";

export function Login({ onLogin, trouble }: { onLogin: (u: User) => void; trouble?: string }) {
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(trouble ?? "");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      onLogin(await api.login(name, password));
    } catch (err) {
      setError(errorText(err));
    }
  };
  return (
    <form className="login" onSubmit={submit}>
      <h1>booksmith</h1>
      <input id="login-name" aria-label="name" placeholder="name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
      <input id="login-password" aria-label="password" type="password" placeholder="password" value={password} onChange={(e) => setPassword(e.target.value)} />
      <button className="primary" type="submit">log in</button>
      {error && <div className="err">{error}</div>}
    </form>
  );
}
