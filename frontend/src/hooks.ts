import { useCallback, useEffect, useRef, useState } from 'react'
import { Job, api } from './api'

export function useApi<T>(loader: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const counter = useRef(0)

  const load = useCallback(async () => {
    const ticket = ++counter.current
    setLoading(true)
    setError(null)
    try {
      const result = await loader()
      if (ticket === counter.current) setData(result)
    } catch (err: any) {
      if (ticket === counter.current) setError(err?.message || 'Request failed')
    } finally {
      if (ticket === counter.current) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    load()
  }, [load])

  return { data, error, loading, reload: load, setData }
}

export function useJobPoller(onComplete?: (job: Job) => void) {
  const [job, setJob] = useState<Job | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<number | null>(null)

  const stop = useCallback(() => {
    if (timer.current) window.clearTimeout(timer.current)
    timer.current = null
  }, [])

  const poll = useCallback(
    async (jobId: string) => {
      try {
        const current = await api.jobs.get(jobId)
        setJob(current)
        if (['completed', 'failed', 'cancelled'].includes(current.status)) {
          stop()
          onComplete?.(current)
          return
        }
        timer.current = window.setTimeout(() => poll(jobId), 900)
      } catch (err: any) {
        setError(err?.message || 'Job polling failed')
        timer.current = window.setTimeout(() => poll(jobId), 2000)
      }
    },
    [onComplete, stop],
  )

  const track = useCallback(
    (jobId: string) => {
      stop()
      setError(null)
      setJob(null)
      poll(jobId)
    },
    [poll, stop],
  )

  useEffect(() => stop, [stop])

  return { job, error, track, stop, setJob }
}
