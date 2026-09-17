import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'

import Dashboard from '../Dashboard'
import Analyze from '../Analyze'
import Clips from '../Clips'
import ClipDetail from '../ClipDetail'
import Planner from '../Planner'
import AutoPilot from '../AutoPilot'
import Settings from '../Settings'
import { api } from '@/lib/api'

const mockNavigate = vi.fn()
let mockSearch = {}
let mockParams = { clipId: 'c1' }

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => mockNavigate,
  useSearch: () => mockSearch,
  useParams: () => mockParams,
  Link: ({ children, to }: any) => <a href={to}>{children}</a>,
}))

let lastSSEOptions: any = null
vi.mock('@/hooks/useSSE', () => ({
  useSSE: (_url: any, options: any) => {
    lastSSEOptions = options
    return null
  },
}))

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      {ui}
    </QueryClientProvider>
  )
}

describe('Pages', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    lastSSEOptions = null
  })

  describe('Dashboard', () => {
    it('renders dashboard with stats and handles recent clips navigation', async () => {
      vi.spyOn(api.clips, 'list').mockResolvedValue([
        { id: 'c1', title: 'Top Play', score: 95, duration: 45, thumbnail_path: '/thumb.jpg' } as any,
        { id: 'c2', title: 'Second Clip', score: 70, duration: 20, thumbnail_path: null } as any,
      ])
      vi.spyOn(api.queue, 'list').mockResolvedValue([{ id: 'q1' } as any])
      vi.spyOn(api.channels, 'list').mockResolvedValue([{ id: 'ch1' } as any])
      vi.spyOn(api.scheduler, 'status').mockResolvedValue({ running: true, cycle_count: 5 } as any)

      renderWithClient(<Dashboard />)

      const input = screen.getByPlaceholderText('https://www.youtube.com/watch?v=...')
      fireEvent.change(input, { target: { value: 'https://youtube.com/watch?v=123' } })

      const button = screen.getByRole('button', { name: 'Klip Üret' })
      fireEvent.click(button)
      expect(mockNavigate).toHaveBeenCalledWith({
        to: '/analyze',
        search: { url: 'https://youtube.com/watch?v=123' },
      })

      await waitFor(() => {
        expect(screen.getByText('Toplam Üretilen Klip')).toBeInTheDocument()
        expect(screen.getByText('Top Play')).toBeInTheDocument()
      })
    })

    it('renders empty recent clips when no clips exist', async () => {
      vi.spyOn(api.clips, 'list').mockResolvedValue([])
      vi.spyOn(api.queue, 'list').mockResolvedValue([])
      vi.spyOn(api.channels, 'list').mockResolvedValue([])
      vi.spyOn(api.scheduler, 'status').mockResolvedValue({ running: false } as any)

      renderWithClient(<Dashboard />)

      await waitFor(() => {
        expect(screen.getByText('Henüz üretilen klip bulunamadı.')).toBeInTheDocument()
        expect(screen.getByText('Durduruldu')).toBeInTheDocument()
      })
    })
  })

  describe('Analyze', () => {
    it('handles pipeline submission, options, and SSE events', async () => {
      vi.spyOn(api.pipeline, 'run').mockResolvedValue({ job_id: 'job-123', status: 'queued' })
      vi.spyOn(api.pipeline, 'getJob').mockResolvedValue({
        id: 'job-123',
        status: 'running',
        progress: 10,
        current_step: 'Video alınıyor',
        logs: [{ time: '18:00', step: 'extract', progress: 10, message: 'Video alınıyor' }],
      } as any)

      renderWithClient(<Analyze />)

      const input = screen.getByPlaceholderText('https://www.youtube.com/watch?v=...')
      fireEvent.change(input, { target: { value: 'https://youtube.com/watch?v=video1' } })

      const numInput = screen.getByRole('spinbutton')
      fireEvent.change(numInput, { target: { value: '5' } })

      const checkboxes = screen.getAllByRole('checkbox')
      checkboxes.forEach((cb) => fireEvent.click(cb))

      const startBtn = screen.getByRole('button', { name: 'Klip Üretimini Başlat' })
      fireEvent.click(startBtn)

      await waitFor(() => {
        expect(screen.getByText('Canlı Pipeline Durumu & Klip Süreçleri')).toBeInTheDocument()
      })

      if (lastSSEOptions?.onInit) {
        lastSSEOptions.onInit({
          status: 'running',
          progress: 25,
          current_step: 'Audio analizi',
          logs: [{ time: '18:01', step: 'audio', progress: 25, message: 'Audio analizi' }],
        })
      }

      if (lastSSEOptions?.onProgress) {
        lastSSEOptions.onProgress({ progress: 45, step: 'llm', message: 'Gemini analiz ediyor...' })
      }
      await waitFor(() => {
        expect(screen.getAllByText('Gemini analiz ediyor...')[0]).toBeInTheDocument()
      })

      if (lastSSEOptions?.onDone) {
        lastSSEOptions.onDone({
          clips: [{ id: 'c1', title: 'Üretilen Klip 1', score: 95, description: 'Desc 1' }],
        })
      }
      await waitFor(() => {
        expect(screen.getByText('Üretilen Klipler (1)')).toBeInTheDocument()
      })

      const resetBtn = screen.getByRole('button', { name: /Yeni Analiz Formu/i })
      fireEvent.click(resetBtn)
    })

    it('handles pipeline error and SSE error', async () => {
      vi.spyOn(api.pipeline, 'run').mockResolvedValue({ job_id: 'job-err', status: 'queued' })
      renderWithClient(<Analyze />)

      const input = screen.getByPlaceholderText('https://www.youtube.com/watch?v=...')
      fireEvent.change(input, { target: { value: 'https://youtube.com/watch?v=err' } })

      const startBtn = screen.getByRole('button', { name: 'Klip Üretimini Başlat' })
      fireEvent.click(startBtn)

      await waitFor(() => {
        expect(screen.getByText('Canlı Pipeline Durumu & Klip Süreçleri')).toBeInTheDocument()
      })

      if (lastSSEOptions?.onError) {
        lastSSEOptions.onError({ message: 'Bağlantı kesildi' })
      }
      await waitFor(() => {
        expect(screen.getAllByText('Bağlantı kesildi')[0]).toBeInTheDocument()
      })
    })

    it('handles pipeline initiation rejection', async () => {
      vi.spyOn(api.pipeline, 'run').mockRejectedValue(new Error('API Hatası'))
      renderWithClient(<Analyze />)

      const input = screen.getByPlaceholderText('https://www.youtube.com/watch?v=...')
      fireEvent.change(input, { target: { value: 'https://youtube.com/watch?v=fail' } })

      const startBtn = screen.getByRole('button', { name: 'Klip Üretimini Başlat' })
      fireEvent.click(startBtn)

      await waitFor(() => {
        expect(screen.getByText('API Hatası')).toBeInTheDocument()
      })
    })

    it('fetches video preview and applies recommended clip count and presets', async () => {
      vi.spyOn(api.videos, 'preview').mockResolvedValue({
        id: 'vid123',
        title: 'Örnek 37 Dakikalık Video',
        duration: 2220,
        duration_minutes: 37,
        duration_formatted: '37:00',
        uploader: 'Test Kanalı',
        thumbnail: 'https://img.youtube.com/vi/vid123/hqdefault.jpg',
        recommended_clips: 10,
        tier_label: 'Orta-Uzun Video',
        explanation: '37 dakikalık video için 8 - 14 arası bol klip önerilir.',
        ranges: [3, 5, 8, 10, 12, 15, 20],
      })

      renderWithClient(<Analyze />)

      const input = screen.getByPlaceholderText('https://www.youtube.com/watch?v=...')
      fireEvent.change(input, { target: { value: 'https://www.youtube.com/watch?v=vid123' } })

      await waitFor(() => {
        expect(screen.getByText('Örnek 37 Dakikalık Video')).toBeInTheDocument()
        expect(screen.getByText('37:00')).toBeInTheDocument()
        expect(screen.getByText(/37 dakikalık video için 8 - 14 arası bol klip önerilir/i)).toBeInTheDocument()
      })

      const applyRecommendedBtn = screen.getByRole('button', { name: /Önerilen 10 Klibi Seç/i })
      fireEvent.click(applyRecommendedBtn)

      const numInput = screen.getByRole('spinbutton') as HTMLInputElement
      expect(numInput.value).toBe('10')

      const presetBtn = screen.getByRole('button', { name: '15' })
      fireEvent.click(presetBtn)
      expect(numInput.value).toBe('15')
    })

    it('handles video preview fetch error silently', async () => {
      vi.spyOn(api.videos, 'preview').mockRejectedValue(new Error('Preview error'))

      renderWithClient(<Analyze />)

      const input = screen.getByPlaceholderText('https://www.youtube.com/watch?v=...')
      fireEvent.change(input, { target: { value: 'https://www.youtube.com/watch?v=errorvid' } })

      await waitFor(() => {
        expect(screen.queryByText('Örnek 37 Dakikalık Video')).not.toBeInTheDocument()
      })
    })
  })

  describe('Clips', () => {
    it('renders list of clips, filters, and handles batch delete modal', async () => {
      vi.spyOn(api.clips, 'list').mockResolvedValue([
        { id: 'c1', video_id: 'v1', title: 'Top Play', score: 95, duration: 45, thumbnail_path: '/thumb.jpg', category: 'HIGHLIGHT', created_at: '2026-09-03T12:00:00' } as any,
        { id: 'c2', video_id: 'v1', title: 'Funny Fail', score: 55, duration: 15, thumbnail_path: null, category: 'FAIL' } as any,
      ])
      vi.spyOn(api.videos, 'list').mockResolvedValue([
        { id: 'v1', title: 'Video 1', uploader: 'Streamer 1' } as any,
      ])
      vi.spyOn(api.videos, 'uploadThumbnail').mockResolvedValue({ success: true, updated_clips_count: 2 } as any)
      vi.spyOn(api.clips, 'thumbnailUrl').mockImplementation((id) => `/api/clips/${id}/thumb`)
      vi.spyOn(api.clips, 'batchDelete').mockResolvedValue({ deleted_count: 1 } as any)
      vi.spyOn(window, 'confirm').mockReturnValue(true)

      renderWithClient(<Clips />)

      await waitFor(() => {
        expect(screen.getByText('Top Play')).toBeInTheDocument()
        expect(screen.getByText('Funny Fail')).toBeInTheDocument()
      })

      const searchInput = screen.getByPlaceholderText('Klip başlığı veya anahtar kelime...')
      fireEvent.change(searchInput, { target: { value: 'Top Play' } })
      expect(screen.getByText('Top Play')).toBeInTheDocument()
      expect(screen.queryByText('Funny Fail')).not.toBeInTheDocument()

      const failBtn = screen.getByRole('button', { name: 'FAIL' })
      fireEvent.click(failBtn)

      const bandBtn = screen.getByRole('button', { name: 'Yüksek' })
      fireEvent.click(bandBtn)

      const deleteModalBtn = screen.getByRole('button', { name: /Klipleri Sil/i })
      fireEvent.click(deleteModalBtn)

      await waitFor(() => {
        expect(screen.getByText('Silinecek Klipleri Seçin')).toBeInTheDocument()
      })

      const lowScoreBtn = screen.getByRole('button', { name: /Düşük Skorlular/i })
      fireEvent.click(lowScoreBtn)

      const clearBtn = screen.getByRole('button', { name: 'Seçimi Temizle' })
      fireEvent.click(clearBtn)

      const allBtn = screen.getByRole('button', { name: /Tümünü Seç/i })
      fireEvent.click(allBtn)

      const clipItems = screen.getAllByText('Top Play')
      if (clipItems[1]) {
        fireEvent.click(clipItems[1])
        fireEvent.click(clipItems[1])
      }

      const confirmDeleteBtn = screen.getByRole('button', { name: /Seçilen Klipleri Sil/i })
      fireEvent.click(confirmDeleteBtn)

      await waitFor(() => {
        expect(api.clips.batchDelete).toHaveBeenCalled()
      })

      // Test Video Thumbnail Modal
      const thumbModalBtn = screen.getByRole('button', { name: /Video Kapağı Yükle/i })
      fireEvent.click(thumbModalBtn)

      await waitFor(() => {
        expect(screen.getByText('Video Kapak Görselleri')).toBeInTheDocument()
        expect(screen.getByText('Video 1')).toBeInTheDocument()
      })

      const uploadForVidBtn = screen.getByRole('button', { name: /Yeni Kapak Yükle/i })
      fireEvent.click(uploadForVidBtn)

      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
      if (fileInput) {
        const file = new File(['dummy'], 'cover.jpg', { type: 'image/jpeg' })
        fireEvent.change(fileInput, { target: { files: [file] } })
      }

      await waitFor(() => {
        expect(api.videos.uploadThumbnail).toHaveBeenCalled()
      })

      const closeThumbModalBtn = screen.getByRole('button', { name: 'Kapat' })
      fireEvent.click(closeThumbModalBtn)
    })
  })

  describe('ClipDetail', () => {
    it('renders clip details, saves edits, and triggers uploads', async () => {
      mockParams = { clipId: 'c1' }
      vi.spyOn(api.clips, 'get').mockResolvedValue({
        id: 'c1',
        title: 'Epic Gaming Moment',
        description: 'Detailed description here',
        tags: 'gaming, viral, shorts',
        score: 85,
        category: 'HIGHLIGHT',
        duration: 35,
        render_path: '/path/to/clip.mp4',
        thumbnail_path: '/path/to/thumb.jpg',
        hook_caption: 'OMG Watch this',
      } as any)
      vi.spyOn(api.clips, 'update').mockResolvedValue({ status: 'ok' } as any)
      vi.spyOn(api.upload, 'youtube').mockResolvedValue({ youtube_url: 'https://youtube.com/shorts/123' } as any)
      vi.spyOn(api.upload, 'instagram').mockResolvedValue({ instagram_url: 'https://instagram.com/reel/123' } as any)
      vi.spyOn(api.queue, 'add').mockResolvedValue({ id: 'q1' } as any)

      renderWithClient(<ClipDetail />)

      await waitFor(() => {
        expect(screen.getByDisplayValue('Epic Gaming Moment')).toBeInTheDocument()
      })

      const descArea = screen.getByDisplayValue('Detailed description here')
      fireEvent.change(descArea, { target: { value: 'Updated description' } })

      const tagsInput = screen.getByDisplayValue('gaming, viral, shorts')
      fireEvent.change(tagsInput, { target: { value: 'gaming, epic' } })

      const saveBtn = screen.getByRole('button', { name: /Değişiklikleri Kaydet/i })
      fireEvent.click(saveBtn)

      const ytBtn = screen.getByRole('button', { name: /YouTube Shorts'a Yükle/i })
      fireEvent.click(ytBtn)

      const igBtn = screen.getByRole('button', { name: /Instagram Reels'e Yükle/i })
      fireEvent.click(igBtn)

      const queueBtn = screen.getByRole('button', { name: /Yayın Takvimine Ekle/i })
      fireEvent.click(queueBtn)

      // Test thumbnail upload in ClipDetail
      vi.spyOn(api.clips, 'uploadVideoThumbnail').mockResolvedValue({ success: true, updated_clips_count: 3 } as any)
      const uploadThumbBtn = screen.getByRole('button', { name: /Yeni Kapak Yükle/i })
      fireEvent.click(uploadThumbBtn)

      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
      if (fileInput) {
        const file = new File(['dummy'], 'cover.jpg', { type: 'image/jpeg' })
        fireEvent.change(fileInput, { target: { files: [file] } })
      }

      await waitFor(() => {
        expect(api.clips.update).toHaveBeenCalled()
        expect(api.upload.youtube).toHaveBeenCalled()
        expect(api.upload.instagram).toHaveBeenCalled()
        expect(api.queue.add).toHaveBeenCalled()
        expect(api.clips.uploadVideoThumbnail).toHaveBeenCalled()
      })
    })

    it('handles delete clip with confirm', async () => {
      mockParams = { clipId: 'c1' }
      vi.spyOn(window, 'confirm').mockReturnValue(true)
      vi.spyOn(api.clips, 'get').mockResolvedValue({
        id: 'c1',
        title: 'Clip to delete',
        score: 70,
      } as any)
      vi.spyOn(api.clips, 'delete').mockResolvedValue({ status: 'ok' } as any)

      renderWithClient(<ClipDetail />)

      await waitFor(() => {
        expect(screen.getByDisplayValue('Clip to delete')).toBeInTheDocument()
      })

      const deleteBtn = screen.getByRole('button', { name: /Sil/i })
      fireEvent.click(deleteBtn)
      await waitFor(() => {
        expect(api.clips.delete).toHaveBeenCalledWith('c1')
      })
    })
  })

  describe('Planner', () => {
    it('renders planner, opens shuffle modal, selects presets, and executes shuffle', async () => {
      vi.spyOn(api.clips, 'list').mockResolvedValue([
        { id: 'c1', title: 'Pool Clip 1', score: 90, duration: 30, thumbnail_path: '/t1.jpg' } as any,
        { id: 'c2', title: 'Pool Clip 2', score: 80, duration: 40, thumbnail_path: null } as any,
      ])
      vi.spyOn(api.queue, 'calendar').mockResolvedValue([
        {
          date: '2026-09-03',
          label: 'Bugün (03 Sep)',
          slots: [
            { time: '11:30', item: { id: 'q1', clip_id: 'c_other', title: 'Viral Clip 1', viral_score: 95, status: 'SCHEDULED' } as any },
            { time: '15:30', item: null },
            { time: '19:00', item: null },
            { time: '22:30', item: null },
          ],
        },
      ] as any)
      vi.spyOn(api.queue, 'shuffle').mockResolvedValue({ message: '1 gün karıştırıldı' } as any)
      vi.spyOn(api.queue, 'add').mockResolvedValue({ id: 'q2' } as any)
      vi.spyOn(api.queue, 'delete').mockResolvedValue({ status: 'ok' } as any)

      renderWithClient(<Planner />)

      await waitFor(() => {
        expect(screen.getByText('Viral Clip 1')).toBeInTheDocument()
        expect(screen.getByText('Pool Clip 1')).toBeInTheDocument()
      })

      const openShuffleBtn = screen.getByRole('button', { name: /Akıllı Dağıt/i })
      fireEvent.click(openShuffleBtn)

      await waitFor(() => {
        expect(screen.getByText('Akıllı Dağıtılacak Günleri Seçin')).toBeInTheDocument()
      })

      const allPresetBtn = screen.getByRole('button', { name: 'Tüm 14 Gün' })
      fireEvent.click(allPresetBtn)

      const next7Btn = screen.getByRole('button', { name: 'İlk 7 Gün' })
      fireEvent.click(next7Btn)

      const clearPresetBtn = screen.getByRole('button', { name: 'Seçimi Temizle' })
      fireEvent.click(clearPresetBtn)

      const next3Btn = screen.getByRole('button', { name: 'İlk 3 Gün' })
      fireEvent.click(next3Btn)

      const dayPills = screen.getAllByText('Bugün (03 Sep)')
      if (dayPills[0]) {
        fireEvent.click(dayPills[0])
        fireEvent.click(dayPills[0])
      }

      const startShuffleBtn = screen.getByRole('button', { name: 'Dağıtımı Başlat' })
      fireEvent.click(startShuffleBtn)
      await waitFor(() => {
        expect(api.queue.shuffle).toHaveBeenCalledWith(['2026-09-03'])
      })

      const addButtons = screen.getAllByTitle('Sıradaki Boş Slota Ekle')
      if (addButtons[0]) {
        fireEvent.click(addButtons[0])
        await waitFor(() => {
          expect(api.queue.add).toHaveBeenCalled()
        })
      }

      const delBtn = screen.getByRole('button', { name: /Çıkar/i })
      fireEvent.click(delBtn)
      await waitFor(() => {
        expect(api.queue.delete).toHaveBeenCalledWith('q1')
      })
    })
  })

  describe('AutoPilot', () => {
    it('renders autopilot page, stops scheduler, deletes channel, and submits new channel', async () => {
      vi.spyOn(api.channels, 'list').mockResolvedValue([
        { id: 'ch1', name: 'Tolunay Ören', url: 'https://youtube.com/@TolunayOren', min_score: 90, active: true, auto_upload: true } as any,
      ])
      vi.spyOn(api.scheduler, 'status').mockResolvedValue({
        running: true,
        video_scanner_running: true,
        clip_publisher_running: true,
        cycle_count: 12,
        last_run: '2026-09-03T10:00:00',
      } as any)
      vi.spyOn(api.scheduler, 'stopVideoScanner').mockResolvedValue({ status: 'stopped' } as any)
      vi.spyOn(api.scheduler, 'stopClipPublisher').mockResolvedValue({ status: 'stopped' } as any)
      vi.spyOn(api.channels, 'create').mockResolvedValue({ id: 'ch2' } as any)
      vi.spyOn(api.channels, 'update').mockResolvedValue({ status: 'ok' } as any)
      vi.spyOn(api.channels, 'delete').mockResolvedValue({ status: 'ok' } as any)
      vi.spyOn(window, 'confirm').mockReturnValue(true)

      renderWithClient(<AutoPilot />)

      await waitFor(() => {
        expect(screen.getByText('Tolunay Ören')).toBeInTheDocument()
        expect(screen.getByText('Taramayı Durdur')).toBeInTheDocument()
        expect(screen.getByText('Paylaşımı Durdur')).toBeInTheDocument()
      })

      const stopScanBtn = screen.getByRole('button', { name: /Taramayı Durdur/i })
      fireEvent.click(stopScanBtn)
      await waitFor(() => {
        expect(api.scheduler.stopVideoScanner).toHaveBeenCalled()
      })

      const stopPubBtn = screen.getByRole('button', { name: /Paylaşımı Durdur/i })
      fireEvent.click(stopPubBtn)
      await waitFor(() => {
        expect(api.scheduler.stopClipPublisher).toHaveBeenCalled()
      })

      const toggleBtn = screen.getByRole('button', { name: 'Durdur' })
      fireEvent.click(toggleBtn)
      await waitFor(() => {
        expect(api.channels.update).toHaveBeenCalled()
      })

      const addModalBtn = screen.getByRole('button', { name: /Yeni Kanal Ekle/i })
      fireEvent.click(addModalBtn)

      const urlInput = screen.getByPlaceholderText('https://www.youtube.com/@KanalAdi')
      const nameInput = screen.getByPlaceholderText('Örn: Tolunay Ören')
      fireEvent.change(urlInput, { target: { value: 'https://youtube.com/@NewChannel' } })
      fireEvent.change(nameInput, { target: { value: 'New Channel' } })

      const submitBtn = screen.getByRole('button', { name: 'Kanalı Kaydet' })
      fireEvent.click(submitBtn)
      await waitFor(() => {
        expect(api.channels.create).toHaveBeenCalled()
      })
    }, 15000)
  })

  describe('Settings', () => {
    it('renders settings page, edits API key, cancels edit, clears cache and DB', async () => {
      vi.spyOn(api.settings, 'get').mockResolvedValue({
        GEMINI_API_KEY: { masked: 'AQ.Ab8...BmVw', set: true },
      } as any)
      vi.spyOn(api.settings, 'getScoring').mockResolvedValue({
        hook_strength_weight: 35,
        emotion_weight: 30,
        story_completeness_weight: 20,
        signal_validation_weight: 15,
        categories: ['CLUTCH', 'FAIL/FUNNY'],
        score_bands: [{ label: 'Yüksek', min: 75, max: 100 }],
        band_labels_enabled: true,
        ensemble_runs: 1,
        mundane_score_cap: 30,
      })
      vi.spyOn(api.settings, 'updateScoring').mockResolvedValue({ updated: true })
      vi.spyOn(api.auth, 'youtubeStatus').mockResolvedValue({ authenticated: true } as any)
      vi.spyOn(api.auth, 'youtubeUrl').mockResolvedValue({ url: 'http://auth' } as any)
      vi.spyOn(api.settings, 'disk').mockResolvedValue({ clip_count: 32, total_bytes: 1024 } as any)
      vi.spyOn(api.settings, 'updateEnv').mockResolvedValue({ status: 'ok' } as any)
      vi.spyOn(api.settings, 'clearCache').mockResolvedValue({ deleted_count: 5 } as any)
      vi.spyOn(api.settings, 'clearDatabase').mockResolvedValue({ status: 'ok' } as any)
      vi.spyOn(window, 'confirm').mockReturnValue(true)
      vi.spyOn(window, 'open').mockImplementation(() => null)

      renderWithClient(<Settings />)

      await waitFor(() => {
        expect(screen.getByText('Google Gemini API Anahtarı')).toBeInTheDocument()
        expect(screen.getByText('Viral Skorlama & Algılama Motoru')).toBeInTheDocument()
      })

      const ytAuthBtn = screen.getByRole('button', { name: /Yeniden Yetkilendir/i })
      fireEvent.click(ytAuthBtn)
      await waitFor(() => {
        expect(api.auth.youtubeUrl).toHaveBeenCalled()
      })

      const editBtn = screen.getByRole('button', { name: 'Değiştir' })
      fireEvent.click(editBtn)

      const cancelBtn = screen.getByRole('button', { name: 'İptal' })
      fireEvent.click(cancelBtn)

      const reEditBtn = screen.getByRole('button', { name: 'Değiştir' })
      fireEvent.click(reEditBtn)

      const keyInput = screen.getByPlaceholderText(/Yeni GEMINI_API_KEY/i)
      fireEvent.change(keyInput, { target: { value: 'new_gemini_key_123' } })

      const saveKeyBtn = screen.getByRole('button', { name: 'Kaydet' })
      fireEvent.click(saveKeyBtn)
      await waitFor(() => {
        expect(api.settings.updateEnv).toHaveBeenCalledWith('GEMINI_API_KEY', 'new_gemini_key_123')
      })

      // Scoring config interactions
      const bandBtn = screen.getByRole('button', { name: 'Aktif' })
      fireEvent.click(bandBtn)
      await waitFor(() => {
        expect(api.settings.updateScoring).toHaveBeenCalled()
      })

      const ensembleBtn = screen.getByRole('button', { name: '1x Tekil' })
      fireEvent.click(ensembleBtn)
      await waitFor(() => {
        expect(api.settings.updateScoring).toHaveBeenCalled()
      })

      const clearCacheBtn = screen.getByRole('button', { name: /Önbelleği Temizle/i })
      fireEvent.click(clearCacheBtn)
      await waitFor(() => {
        expect(api.settings.clearCache).toHaveBeenCalled()
      })

      const resetDbBtn = screen.getByRole('button', { name: /Sıfırla/i })
      fireEvent.click(resetDbBtn)
      await waitFor(() => {
        expect(api.settings.clearDatabase).toHaveBeenCalledWith(true)
      })
    })
  })
})
