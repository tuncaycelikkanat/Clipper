import { describe, it, expect, vi, beforeEach } from 'vitest'
import { api } from '../api'

describe('api client', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('handles successful requests and various HTTP methods', async () => {
    const mockJson = { success: true }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockJson,
    })
    globalThis.fetch = fetchMock

    // pipeline
    expect(await api.pipeline.run({ url: 'http://yt' })).toEqual(mockJson)
    expect(await api.pipeline.getJob('j1')).toEqual(mockJson)
    expect(await api.pipeline.listJobs()).toEqual(mockJson)
    expect(await api.pipeline.cancelJob('j1')).toEqual(mockJson)
    expect(api.pipeline.streamUrl('j1')).toContain('/api/pipeline/jobs/j1/stream')

    // clips
    expect(await api.clips.list({ limit: 10 })).toEqual(mockJson)
    expect(await api.clips.get('c1')).toEqual(mockJson)
    expect(await api.clips.update('c1', { title: 'New' })).toEqual(mockJson)
    expect(await api.clips.delete('c1')).toEqual(mockJson)
    expect(await api.clips.uploadVideoThumbnail('c1', new File([''], 'thumb.jpg', { type: 'image/jpeg' }))).toEqual(mockJson)
    expect(api.clips.fileUrl('c1')).toContain('/api/clips/c1/file')
    expect(api.clips.thumbnailUrl('c1')).toContain('/api/clips/c1/thumbnail')

    // videos
    expect(await api.videos.list()).toEqual(mockJson)
    expect(await api.videos.get('v1')).toEqual(mockJson)
    expect(await api.videos.uploadThumbnail('v1', new File([''], 'thumb.jpg', { type: 'image/jpeg' }))).toEqual(mockJson)

    // channels
    expect(await api.channels.list()).toEqual(mockJson)
    expect(await api.channels.create({ url: 'http://c', name: 'C', min_score: 90, auto_upload: true })).toEqual(mockJson)
    expect(await api.channels.update('ch1', { name: 'C2' })).toEqual(mockJson)
    expect(await api.channels.delete('ch1')).toEqual(mockJson)

    // queue
    expect(await api.queue.list({ status: 'pool' })).toEqual(mockJson)
    expect(await api.queue.add({ clip_id: 'c1' })).toEqual(mockJson)
    expect(await api.queue.update('q1', { status: 'scheduled' })).toEqual(mockJson)
    expect(await api.queue.delete('q1')).toEqual(mockJson)
    expect(await api.queue.calendar()).toEqual(mockJson)
    expect(await api.queue.shuffle()).toEqual(mockJson)

    // scheduler
    expect(await api.scheduler.start(2.0)).toEqual(mockJson)
    expect(await api.scheduler.stop()).toEqual(mockJson)
    expect(await api.scheduler.status()).toEqual(mockJson)

    // upload
    expect(await api.upload.youtube('c1')).toEqual(mockJson)
    expect(await api.upload.instagram('c1')).toEqual(mockJson)
    expect(await api.upload.tiktok('c1')).toEqual(mockJson)

    // auth
    expect(await api.auth.youtubeUrl()).toEqual(mockJson)
    expect(await api.auth.youtubeStatus()).toEqual(mockJson)

    // settings
    expect(await api.settings.get()).toEqual(mockJson)
    expect(await api.settings.updateEnv('KEY', 'VAL')).toEqual(mockJson)
    expect(await api.settings.clearCache()).toEqual(mockJson)
    expect(await api.settings.clearDatabase(true)).toEqual(mockJson)
    expect(await api.settings.disk()).toEqual(mockJson)
    expect(await api.settings.getScoring()).toEqual(mockJson)
    expect(await api.settings.updateScoring({ band_labels_enabled: true })).toEqual(mockJson)
  })

  it('throws error when response.ok is false', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
    })

    await expect(api.videos.get('missing')).rejects.toThrow('API error: 404 Not Found')
  })
})
