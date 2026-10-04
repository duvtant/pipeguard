import { useState } from 'react'
import { cx } from './Card'

const BG = ['bg-av-sky', 'bg-av-lilac', 'bg-av-blush', 'bg-av-mint', 'bg-av-sand', 'bg-av-teal']
export const avatarBg = (i: number) => BG[i % BG.length]

/** Letter bubble in a pastel, or a photo when `src` is given. If the photo is missing it falls back to the letter, so a person
 *  without a headshot never shows a broken image. `square` is the org switcher; round is for people. */
export function Avatar({ letter, tone = 0, size = 36, square, src, className }: { letter: string; tone?: number; size?: number; square?: boolean; src?: string; className?: string }) {
  const [broken, setBroken] = useState(false)
  const shape = square ? 'rounded-[10px]' : 'rounded-full'
  if (src && !broken) {
    // The headshots are framed wide (shoulders and background). In a small circle the face would be tiny, so zoom in on the face:
    // eyes sit about 40% from the top, so scale up around that point.
    return (
      <span style={{ width: size, height: size }} className={cx('relative flex-none overflow-hidden', shape, avatarBg(tone), className)}>
        <img src={src} alt="" width={size} height={size} loading="lazy" decoding="async" onError={() => setBroken(true)} className="size-full origin-[50%_36%] scale-[1.55] object-cover" />
      </span>
    )
  }
  return (
    <span aria-hidden style={{ width: size, height: size }} className={cx('grid flex-none place-items-center text-sm font-semibold text-[#1d3f55]', shape, avatarBg(tone), className)}>{letter}</span>
  )
}
