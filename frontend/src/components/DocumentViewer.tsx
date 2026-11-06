import { FileText, X } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { DOC_LABELS, type DocType, type SourceRef } from '../api'
import { btn } from './ui'

export type DocTarget = { docType: DocType; source: SourceRef | null; label: string }

/**
 * The extracted text of one document, page by page with line numbers, opened at the line a finding cites.
 * Line numbers count every line of a page, blank ones included, exactly as the server records them.
 */
export default function DocumentViewer({ target, text, filename, onClose }: {
  target: DocTarget | null
  text: string | undefined
  filename: string | undefined
  onClose: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const hit = useRef<HTMLLIElement>(null)
  useEffect(() => {
    const d = ref.current
    if (target && !d?.open) d?.showModal()
    if (!target && d?.open) d.close()
    if (target) requestAnimationFrame(() => hit.current?.scrollIntoView({ block: 'center' }))
  }, [target])
  const pages = (text ?? '').split('\f')
  const s = target?.source

  return (
    <dialog ref={ref} aria-labelledby="doc-viewer-title" onCancel={(e) => { e.preventDefault(); onClose() }}
      onClick={(e) => e.target === ref.current && onClose()}
      className="m-auto h-[min(48rem,calc(100dvh-2rem))] w-[min(56rem,calc(100vw-2rem))] overflow-hidden rounded-[28px] bg-tile p-0 text-ink-2 shadow-[0_24px_64px_-16px_rgb(0_0_0/0.3)] open:flex open:animate-toast-in open:flex-col backdrop:bg-black/40 backdrop:animate-fade-in">
      {target && (
        <>
          <header className="flex items-start justify-between gap-4 px-5 pt-5 pb-4 sm:px-7">
            <div className="min-w-0">
              <h2 id="doc-viewer-title" className="text-[17px] font-semibold text-ink">{DOC_LABELS[target.docType]}</h2>
              <p className="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 text-sm text-mute">
                <FileText aria-hidden className="size-3.5 shrink-0" strokeWidth={1.75} />
                <span className="truncate">{filename ?? 'Uploaded document'}</span>
                <span aria-hidden className="text-faint">·</span>
                <span>{target.label}{s ? ` · page ${s.page}, line ${s.line}` : ''}</span>
              </p>
            </div>
            <button className={btn.icon} onClick={onClose} aria-label="Close document"><X className="size-5" /></button>
          </header>
          <div className="min-h-0 flex-1 overflow-auto px-2 pb-2 sm:px-3 sm:pb-3">
            {!text ? (
              <p className="px-5 py-10 text-[15px] text-mute">The extracted text of this document is not available.</p>
            ) : (
              <div className="space-y-3">
                {pages.map((page, pi) => (
                  <section key={pi} aria-label={`Page ${pi + 1}`} className="rounded-xl bg-paper py-4 shadow-[0_1px_3px_rgb(0_0_0/0.06)]">
                    {pages.length > 1 && <p className="px-5 pb-2 text-xs font-medium text-mute">Page {pi + 1} of {pages.length}</p>}
                    <ol className="font-mono text-[12.5px] leading-6">
                      {page.split('\n').map((line, li) => {
                        const isHit = !!s && s.page === pi + 1 && s.line === li + 1
                        return (
                          <li key={li} ref={isHit ? hit : undefined} aria-current={isHit || undefined}
                            className={`grid grid-cols-[3rem_1fr] pr-5 ${isHit ? 'bg-accent-fill/10 ring-1 ring-inset ring-accent-fill' : ''}`}>
                            <span aria-hidden className="select-none pr-3 text-right tabular-nums text-faint">{li + 1}</span>
                            <span className="whitespace-pre-wrap break-words text-ink-2">{line || ' '}</span>
                          </li>
                        )
                      })}
                    </ol>
                  </section>
                ))}
              </div>
            )}
          </div>
          {!s && text && (
            <p className="px-6 pb-4 text-[13px] text-mute">No line location was recorded for this item (it was entered or edited by hand, or comes from a demo fixture).</p>
          )}
        </>
      )}
    </dialog>
  )
}
