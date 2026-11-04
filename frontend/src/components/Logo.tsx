export default function Logo() {
  return (
    <span className="flex items-center gap-2 text-ink">
      <svg aria-hidden viewBox="0 0 32 32" className="size-[22px]">
        <rect width="32" height="32" rx="8" fill="currentColor" />
        <path d="M21.5 10.5a8 8 0 1 0 0 11" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
        <circle cx="21.5" cy="16" r="2.1" fill="#0071e3" />
      </svg>
      <span className="text-[17px] font-semibold tracking-[-0.02em]">Clavion</span>
    </span>
  )
}
