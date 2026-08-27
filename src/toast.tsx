// ==============================================================================
// 长流水前端 · 全局 Toast（移植原型 toast 行为：2.6s 自动消散）
// ==============================================================================
import { useEffect, useState } from 'react';

let push: (msg: string) => void = () => {};

/** 任意模块可调用：toast('已落笔 …') */
export function toast(msg: string) {
  push(msg);
}

export function ToastHost() {
  const [msg, setMsg] = useState('');
  const [show, setShow] = useState(false);

  useEffect(() => {
    let timer = 0;
    push = (m: string) => {
      setMsg(m);
      setShow(true);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setShow(false), 2600);
    };
    return () => {
      push = () => {};
      window.clearTimeout(timer);
    };
  }, []);

  return <div className={`toast${show ? ' show' : ''}`}>{msg}</div>;
}
