import { FormEvent, useCallback, useEffect, useState } from "react";

import { api, errorText } from "../api";
import type { LedgerRow, ModelEntry, Placement, User } from "../types";

export function Admin() {
  const [text, setText] = useState("");
  const [users, setUsers] = useState<User[]>([]);
  const [placements, setPlacements] = useState<Placement[]>([]);
  const [ledger, setLedger] = useState<LedgerRow[]>([]);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const fail = (e: unknown) => { setError(errorText(e)); setNote(""); };
  const ok = (text: string) => { setNote(text); setError(""); };

  const loadModels = useCallback(() => api.models().then((m) => setText(JSON.stringify(m, null, 1)), fail), []);
  const loadUsers = useCallback(() => api.users().then(setUsers, fail), []);
  const loadFleet = useCallback(() => {
    api.placements().then(setPlacements, () => setPlacements([]));
    api.ledger().then(setLedger, () => setLedger([]));
  }, []);
  useEffect(() => {
    loadModels();
    loadUsers();
    loadFleet();
    const t = setInterval(loadFleet, 10000);
    return () => clearInterval(t);
  }, [loadModels, loadUsers, loadFleet]);

  const save = async () => {
    let body: Record<string, ModelEntry>;
    try {
      body = JSON.parse(text);
    } catch (e) {
      fail(new Error(`not JSON: ${errorText(e)}`));
      return;
    }
    try {
      const got = await api.putModels(body);
      setText(JSON.stringify(got, null, 1));
      ok(`saved ${Object.keys(got).length} models`);
    } catch (e) {
      fail(e);
    }
  };

  return (
    <>
      <h1>Admin</h1>
      {error && <div className="err">{error}</div>}
      {note && <div className="ok">{note}</div>}
      <div className="grid2">
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>Models</h2>
          <div className="muted">One entry per model: kind, an endpoint or an image with its provider, knobs, api_key, idle_s, budget_usd.</div>
          <textarea id="models-json" aria-label="models" className="json" value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} />
          <div className="row"><button className="primary" onClick={save}>save</button><button onClick={loadModels}>reload</button></div>
        </div>
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>Users</h2>
          <table><tbody>{users.map((u) => <tr key={u.id}><td>{u.id}</td><td>{u.name}</td><td className="muted">{u.role}</td></tr>)}</tbody></table>
          <AddUser onDone={(name) => { loadUsers(); ok(`added ${name}`); }} onError={fail} />
        </div>
      </div>
      <h2>Placements</h2>
      <table>
        <thead><tr><th>model</th><th>provider</th><th>state</th><th>endpoint</th><th>$/h</th><th>started</th><th></th></tr></thead>
        <tbody>
          {placements.length === 0 && <tr><td colSpan={7} className="muted">nothing is running</td></tr>}
          {placements.map((p) => (
            <tr key={p.id}>
              <td>{p.model}</td><td>{p.provider}</td><td><span className={`pill ${p.state === "ready" ? "done" : "running"}`}>{p.state}</span></td>
              <td className="mono">{p.endpoint}</td><td>{p.rate_usd_h.toFixed(2)}</td><td>{new Date(p.started * 1000).toLocaleTimeString()}</td>
              <td><button onClick={() => api.stopPlacement(p.id).then(loadFleet, fail)}>stop</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2>Ledger</h2>
      <table>
        <thead><tr><th>model</th><th>provider</th><th>started</th><th>stopped</th><th>cost $</th><th>why</th></tr></thead>
        <tbody>
          {ledger.slice(-20).reverse().map((r, i) => (
            <tr key={i}><td>{r.model}</td><td>{r.provider}</td><td>{new Date(r.started * 1000).toLocaleString()}</td><td>{new Date(r.stopped * 1000).toLocaleTimeString()}</td><td>{r.cost_usd.toFixed(3)}</td><td>{r.why}</td></tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function AddUser({ onDone, onError }: { onDone: (name: string) => void; onError: (e: unknown) => void }) {
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("user");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.addUser(name, password, role);
      setName("");
      setPassword("");
      onDone(name);
    } catch (err) {
      onError(err);
    }
  };
  return (
    <form className="row" onSubmit={submit}>
      <input id="user-name" aria-label="user name" placeholder="name" value={name} onChange={(e) => setName(e.target.value)} />
      <input id="user-password" aria-label="password" type="password" placeholder="password" value={password} onChange={(e) => setPassword(e.target.value)} />
      <select id="user-role" aria-label="role" value={role} onChange={(e) => setRole(e.target.value)}><option>user</option><option>admin</option></select>
      <button type="submit">add</button>
    </form>
  );
}
