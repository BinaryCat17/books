# -*- coding: utf-8 -*-
import sys, os, collections
sys.path.insert(0,os.path.expanduser("~/booksmith-work/e3/bin"))
from base import *
sys.path.insert(0, os.path.expanduser("~/booksmith-work/cc1/src"))
from booksmith import merge as NEW
sys.path.insert(0, os.path.join(W,"src"))
T=collections.Counter()
print(f"{'книга':16} {'ячеек':>7} {'пустых':>7} {'помечено':>9} {'доля':>6} {'с вариантами':>13}")
for b in BOOKS:
    ds=drafts(b)
    out,mk,tot,emp = NEW.mark_cells(ds[0], ds[1:])
    wt = out.count('title="чтения разошлись')
    print(f"{b:16} {tot:7} {emp:7} {mk:9} {mk/tot:6.1%} {wt:13}")
    T["t"]+=tot;T["e"]+=emp;T["m"]+=mk;T["w"]+=wt
    # идемпотентность
    out2,mk2,tot2,emp2 = NEW.mark_cells(out, ds[1:])
    assert out2==out, f"{b}: второй прогон изменил текст"
    assert (mk2,tot2,emp2)==(mk,tot,emp), f"{b}: числа разошлись {mk2,tot2,emp2}"
print(f"{'ИТОГО':16} {T['t']:7} {T['e']:7} {T['m']:9} {T['m']/T['t']:6.1%} {T['w']:13}")
print("идемпотентность mark_cells: второй прогон байт в байт — да")
