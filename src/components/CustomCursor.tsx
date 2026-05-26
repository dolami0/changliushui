import { useEffect, useRef } from 'react';

export default function CustomCursor() {
  const cursorRef = useRef<HTMLDivElement>(null);
  const hoverRef = useRef(false);

  useEffect(() => {
    const cursor = cursorRef.current;
    if (!cursor) return;

    let mouseX = -100;
    let mouseY = -100;
    let currentX = -100;
    let currentY = -100;
    let rafId = 0;

    const onMouseMove = (e: MouseEvent) => {
      mouseX = e.clientX;
      mouseY = e.clientY;
    };

    const onMouseOver = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (
        target.tagName === 'A' ||
        target.tagName === 'BUTTON' ||
        target.closest('a') ||
        target.closest('button') ||
        target.dataset.hover === 'true'
      ) {
        hoverRef.current = true;
      }
    };

    const onMouseOut = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (
        target.tagName === 'A' ||
        target.tagName === 'BUTTON' ||
        target.closest('a') ||
        target.closest('button') ||
        target.dataset.hover === 'true'
      ) {
        hoverRef.current = false;
      }
    };

    const animate = () => {
      currentX = mouseX;
      currentY = mouseY;

      if (cursor) {
        cursor.style.transform = `translate(calc(${currentX}px - 50%), calc(${currentY}px - 50%))`;
        cursor.classList.toggle('cc-hover', hoverRef.current);
        document.body.classList.toggle('cc-hovering', hoverRef.current);
      }

      rafId = requestAnimationFrame(animate);
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseover', onMouseOver);
    document.addEventListener('mouseout', onMouseOut);
    rafId = requestAnimationFrame(animate);

    return () => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseover', onMouseOver);
      document.removeEventListener('mouseout', onMouseOut);
      cancelAnimationFrame(rafId);
    };
  }, []);

  return (
    <>
      <style>{`
        .cc-ring {
          position: fixed; top: 0; left: 0; z-index: 9999; pointer-events: none;
          width: 0; height: 0;
          border: 0 solid #ADFF00;
          box-shadow: none;
          transition: width 0.15s, height 0.15s, border 0.15s, box-shadow 0.15s;
        }
        .cc-ring.cc-hover {
          width: 22px; height: 22px;
          border: 1.5px solid #ADFF00;
          box-shadow: 0 0 8px rgba(173,255,0,0.5), 0 0 20px rgba(173,255,0,0.2);
        }
        @media (max-width: 768px) {
          .cc-ring, .cc-ring.cc-hover { display: none; }
        }
        /* 环显示时隐藏系统手型光标 */
        body.cc-hovering, body.cc-hovering * { cursor: none !important; }
      `}</style>
      <div ref={cursorRef} className="cc-ring" />
    </>
  );
}
