import { useEffect, useRef, useState } from 'react';

const LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*';
const CN_LETTERS = '甲乙丙丁戊己庚辛壬癸乾坤震巽坎离艮兑虚实阴阳';

interface GlitchTextProps {
  text: string;
  className?: string;
  style?: React.CSSProperties;
  as?: 'span' | 'div' | 'p' | 'h1' | 'h2' | 'h3';
}

export default function GlitchText({
  text,
  className = '',
  style = {},
  as: Tag = 'span',
}: GlitchTextProps) {
  const [display, setDisplay] = useState(text);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const hasAnimated = useRef(false);

  useEffect(() => {
    if (hasAnimated.current) {
      setDisplay(text);
      return;
    }
    hasAnimated.current = true;

    let iteration = 0;
    const allChars = LETTERS + CN_LETTERS;

    intervalRef.current = setInterval(() => {
      setDisplay(
        text
          .split('')
          .map((char, index) => {
            if (char === ' ' || char === '\n') return char;
            if (index < iteration) return text[index];
            return allChars[Math.floor(Math.random() * allChars.length)];
          })
          .join('')
      );

      iteration += 1 / 2;

      if (iteration >= text.length) {
        if (intervalRef.current) clearInterval(intervalRef.current);
        setDisplay(text);
      }
    }, 30);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [text]);

  return (
    <Tag
      className={className}
      style={{
        ...style,
        animation: 'glitch 0.3s ease-out',
      }}
    >
      {display}
    </Tag>
  );
}
