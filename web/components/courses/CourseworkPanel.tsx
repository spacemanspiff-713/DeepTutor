'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import {
  ArrowRight,
  BookOpenCheck,
  ChevronDown,
  ClipboardCheck,
  FolderKanban,
  GraduationCap,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'

import AssistantResponse from '@/components/common/AssistantResponse'
import { courseApi } from '@/lib/course-api'
import type { CourseClass, CourseDetail } from '@/lib/course-types'

/**
 * The unique part of the former Interactive Courses workspace, embedded in the
 * native course container during migration.
 *
 * Native Courses owns the syllabus, materials, mastery, reading, notebooks,
 * progress, and conversations. This panel reads only the artifact layer the
 * native product does not yet model: tutorials, assignments, and projects.
 */
export default function CourseworkPanel({ courseId }: { courseId: string }) {
  const { t } = useTranslation()
  const [detail, setDetail] = useState<CourseDetail | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    void courseApi
      .get(courseId)
      .then(next => {
        if (!cancelled) setDetail(next)
      })
      .catch(() => {
        // A native-only course has no legacy artifact bundle. Its page should
        // not gain an error banner for an optional extension it never used.
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [courseId])

  const totals = useMemo(() => {
    const classes = detail?.classes ?? []
    return {
      compiled: classes.filter(item => item.content_status === 'ready').length,
      tutorials: classes.reduce((sum, item) => sum + item.tutorials.length, 0),
      assignments: classes.reduce((sum, item) => sum + item.assignments.length, 0),
      projects: classes.filter(
        item => item.content_status === 'ready' && item.project.title
      ).length,
    }
  }, [detail])

  if (!loading && !detail) return null

  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 font-serif text-[16px] font-semibold text-[var(--foreground)]">
            <FolderKanban size={15} strokeWidth={1.7} />
            {t('Coursework')}
          </h2>
          <p className="mt-0.5 text-[11.5px] leading-relaxed text-[var(--muted-foreground)]">
            {t('Tutorials, assignments, and projects generated for this course.')}
          </p>
        </div>
        {detail ? (
          <Link
            href={`/interactive-courses?course=${encodeURIComponent(courseId)}`}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--background)] px-2.5 py-1.5 text-[11.5px] font-medium text-[var(--foreground)] transition-colors hover:bg-[var(--muted)]/50"
          >
            {t('Open coursework board')}
            <ArrowRight size={12} />
          </Link>
        ) : null}
      </div>

      {loading ? (
        <div className="mt-4 h-20 animate-pulse rounded-xl bg-[var(--muted)]" />
      ) : detail ? (
        <>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Metric
              icon={GraduationCap}
              value={`${totals.compiled}/${detail.classes.length}`}
              label={t('workspaces ready')}
            />
            <Metric icon={BookOpenCheck} value={String(totals.tutorials)} label={t('tutorials')} />
            <Metric
              icon={ClipboardCheck}
              value={String(totals.assignments)}
              label={t('assignments')}
            />
            <Metric icon={FolderKanban} value={String(totals.projects)} label={t('projects')} />
          </div>

          <div className="mt-3 space-y-1">
            {detail.classes.map(item => (
              <ClassArtifacts key={item.id} item={item} />
            ))}
          </div>
        </>
      ) : null}
    </section>
  )
}

function Metric({
  icon: Icon,
  value,
  label,
}: {
  icon: typeof GraduationCap
  value: string
  label: string
}) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--background)] px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-[var(--muted-foreground)]">
        <Icon size={12} strokeWidth={1.7} />
        <span className="text-[10.5px]">{label}</span>
      </div>
      <p className="mt-1 font-serif text-[17px] font-semibold text-[var(--foreground)]">{value}</p>
    </div>
  )
}

function ClassArtifacts({ item }: { item: CourseClass }) {
  const { t } = useTranslation()
  const ready = item.content_status === 'ready'
  return (
    <details className="group rounded-xl border border-[var(--border)] bg-[var(--background)]">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5">
        <ChevronDown
          size={13}
          className="shrink-0 text-[var(--muted-foreground)] transition-transform group-open:rotate-180"
        />
        <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium text-[var(--foreground)]">
          {item.order + 1}. {item.title}
        </span>
        <span className="shrink-0 text-[10.5px] text-[var(--muted-foreground)]">
          {ready
            ? t('{{tutorials}} tutorials · {{assignments}} assignments', {
                tutorials: item.tutorials.length,
                assignments: item.assignments.length,
              })
            : t('Planned')}
        </span>
      </summary>
      <div className="border-t border-[var(--border)] px-4 py-3">
        {!ready ? (
          <div>
            <p className="text-[12px] leading-relaxed text-[var(--muted-foreground)]">
              {item.summary || t('This class workspace will be generated when you reach it.')}
            </p>
            <p className="mt-2 text-[11px] text-[var(--muted-foreground)]/80">
              {t('Open the coursework board to generate its artifacts.')}
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {item.tutorials.map(tutorial => (
              <details key={tutorial.id} className="rounded-lg bg-[var(--card)] p-3">
                <summary className="cursor-pointer text-[12px] font-medium text-[var(--foreground)]">
                  {tutorial.title}
                  <span className="ml-2 text-[10.5px] font-normal text-[var(--muted-foreground)]">
                    {t('{{minutes}} min · {{status}}', {
                      minutes: tutorial.estimated_minutes,
                      status: tutorial.status.replace('_', ' '),
                    })}
                  </span>
                </summary>
                <AssistantResponse content={tutorial.content} className="mt-3 text-sm" />
              </details>
            ))}
            {item.assignments.map(assignment => (
              <details key={assignment.id} className="rounded-lg bg-[var(--card)] p-3">
                <summary className="cursor-pointer text-[12px] font-medium text-[var(--foreground)]">
                  {assignment.title}
                  <span className="ml-2 text-[10.5px] font-normal text-[var(--muted-foreground)]">
                    {assignment.status.replace('_', ' ')}
                  </span>
                </summary>
                <div className="mt-3 space-y-3 text-[12px] leading-relaxed">
                  <p className="whitespace-pre-wrap">{assignment.prompt}</p>
                  <div>
                    <p className="font-medium">{t('Deliverable')}</p>
                    <p className="mt-1 text-[var(--muted-foreground)]">{assignment.deliverable}</p>
                  </div>
                  <div>
                    <p className="font-medium">{t('Rubric')}</p>
                    <ul className="mt-1 list-disc space-y-1 pl-5 text-[var(--muted-foreground)]">
                      {assignment.rubric.map(criterion => (
                        <li key={criterion}>{criterion}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </details>
            ))}
            {item.project.title ? (
              <details className="rounded-lg bg-[var(--card)] p-3">
                <summary className="cursor-pointer text-[12px] font-medium text-[var(--foreground)]">
                  {item.project.title}
                  <span className="ml-2 text-[10.5px] font-normal text-[var(--muted-foreground)]">
                    {item.project.progress}%
                  </span>
                </summary>
                <div className="mt-3 space-y-3 text-[12px] leading-relaxed">
                  <p className="whitespace-pre-wrap text-[var(--muted-foreground)]">
                    {item.project.brief}
                  </p>
                  <ArtifactList title={t('Milestones')} items={item.project.milestones} />
                  <ArtifactList
                    title={t('Success criteria')}
                    items={item.project.success_criteria}
                  />
                </div>
              </details>
            ) : null}
          </div>
        )}
      </div>
    </details>
  )
}

function ArtifactList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null
  return (
    <div>
      <p className="font-medium">{title}</p>
      <ul className="mt-1 list-disc space-y-1 pl-5 text-[var(--muted-foreground)]">
        {items.map(item => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  )
}
