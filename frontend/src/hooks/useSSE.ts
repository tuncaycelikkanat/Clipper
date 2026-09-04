import { useEffect, useRef } from 'react';
import { SSEProgressEvent } from '../types';

export function useSSE(url: string | null, options: {
  onInit?: (data: any) => void;
  onProgress?: (event: SSEProgressEvent) => void;
  onDone?: (data: any) => void;
  onError?: (error: any) => void;
}) {
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!url) return;

    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    const handleData = (callback?: (data: any) => void) => (event: MessageEvent) => {
      try {
        const parsed = JSON.parse(event.data);
        if (callback) callback(parsed);
      } catch (e) {
        console.error('Failed to parse SSE event data', e);
      }
    };

    if (options.onInit) {
      eventSource.addEventListener('init', handleData(options.onInit));
    }
    if (options.onProgress) {
      eventSource.addEventListener('progress', handleData(options.onProgress));
    }
    if (options.onDone) {
      eventSource.addEventListener('done', handleData(options.onDone));
    }
    if (options.onError) {
      eventSource.addEventListener('error', handleData(options.onError));
    }

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'init' && options.onInit) options.onInit(data.data || data);
        else if (data.type === 'progress' && options.onProgress) options.onProgress(data.data || data);
        else if (data.type === 'done' && options.onDone) options.onDone(data.data || data);
        else if (data.type === 'error' && options.onError) options.onError(data.data || data);
      } catch (e) {
        // Heartbeat or raw message
      }
    };

    eventSource.onerror = (error) => {
      // If readyState is closed, trigger error
      if (eventSource.readyState === EventSource.CLOSED && options.onError) {
        options.onError({ message: 'Bağlantı kapandı.' });
      }
    };

    return () => {
      eventSource.close();
    };
  }, [url]);

  return eventSourceRef.current;
}
