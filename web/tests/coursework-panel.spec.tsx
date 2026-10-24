import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import CourseworkPanel from '@/components/courses/CourseworkPanel'
import type { CourseDetail } from '@/lib/course-types'

const fixture = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) => {
      if (!values) return key
      return Object.entries(values).reduce(
        (text, [name, value]) => text.replace(`{{${name}}}`, String(value)),
        key
      )
    },
  }),
}))
vi.mock('@/lib/course-api', () => ({
  courseApi: { get: (...args: unknown[]) => fixture.get(...args) },
}))
vi.mock('@/components/common/AssistantResponse', () => ({
  default: ({ content }: { content: string }) => <div>{content}</div>,
}))

function detail(): CourseDetail {
  return {
    course: {
      id: 'course_legacy',
      title: 'Legacy course',
      description: '',
      status: 'ready',
      proposal: null,
      knowledge_bases: [],
      resource_links: [],
      language: 'en',
      class_count: 1,
      completed_class_count: 0,
      created_at: 1,
      updated_at: 1,
    },
    outline: null,
    progress: {
      course_id: 'course_legacy',
      current_class_id: 'class_one',
      completed_class_ids: [],
      updated_at: 1,
    },
    classes: [
      {
        id: 'class_one',
        course_id: 'course_legacy',
        title: 'Foundations',
        summary: 'Start here',
        order: 0,
        status: 'next',
        learning_objectives: ['Explain the system'],
        knowledge_points: [],
        prerequisite_ids: [],
        resource_ids: [],
        book_ids: [],
        content_status: 'ready',
        content_error: '',
        tutorials: [
          {
            id: 'tutorial_one',
            title: 'Guided walkthrough',
            content: 'Tutorial body',
            estimated_minutes: 20,
            status: 'not_started',
          },
        ],
        assignments: [
          {
            id: 'assignment_one',
            title: 'Build it',
            prompt: 'Create the implementation.',
            deliverable: 'A repository',
            rubric: ['It works'],
            status: 'todo',
            learner_submission: '',
            feedback: '',
          },
        ],
        notes: '',
        project: {
          title: 'Capstone',
          brief: 'Ship it',
          milestones: ['Prototype'],
          success_criteria: ['Tested'],
          progress: 0,
        },
        chat_session_id: '',
        updated_at: 1,
      },
    ],
  }
}

beforeEach(() => fixture.get.mockReset())
afterEach(() => cleanup())

it('embeds legacy coursework inside a native course', async () => {
  fixture.get.mockResolvedValue(detail())
  render(<CourseworkPanel courseId="course_legacy" />)

  expect(await screen.findByText('Coursework')).toBeInTheDocument()
  expect(screen.getByText('1/1')).toBeInTheDocument()
  expect(screen.getByText(/Foundations/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /Open coursework board/ })).toHaveAttribute(
    'href',
    '/interactive-courses?course=course_legacy'
  )
})

it('stays absent for a native-only course', async () => {
  fixture.get.mockResolvedValue(null)
  render(<CourseworkPanel courseId="course_native" />)

  await waitFor(() => expect(screen.queryByText('Coursework')).toBeNull())
})
