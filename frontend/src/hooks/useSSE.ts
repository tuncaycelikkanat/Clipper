import { useEffect, useRef } from 'react';
import { SSEProgressEvent } from '../types';

export function useSSE(url: string | null, options: {
  onInit?: (data: any) => void;
  onProgress?: (event: SSEProgressEvent) => void;
  onDone?: (data: any) => void;
  onError?: (error: any) => void;
}) {
  const eventSourceRef = useRef<EventSource | null>(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  useEffect(() => {
    if (!url) return;

    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    const handleData = (eventType: 'init' | 'progress' | 'done' | 'error') => (event: MessageEvent) => {
      try {
        const parsed = JSON.parse(event.data);
        const cb = optionsRef.current[eventType === 'init' ? 'onInit' : eventType === 'progress' ? 'onProgress' : eventType === 'done' ? 'onDone' : 'onError'];
        if (cb) cb(parsed);
      } catch (e) {
        console.error('Failed to parse SSE event data', e);
      }
    };

    eventSource.addEventListener('init', handleData('init'));
    eventSource.addEventListener('progress', handleData('progress'));
    eventSource.addEventListener('done', handleData('done'));
    eventSource.addEventListener('error', handleData('error'));

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'init' && optionsRef.current.onInit) optionsRef.current.onInit(data.data || data);
        else if (data.type === 'progress' && optionsRef.current.onProgress) optionsRef.current.onProgress(data.data || data);
        else if (data.type === 'done' && optionsRef.current.onDone) optionsRef.current.onDone(data.data || data);
        else if (data.type === 'error' && optionsRef.current.onError) optionsRef.current.onError(data.data || data);
      } catch (e) {
        // Heartbeat or raw message
      }
    };

    eventSource.onerror = (error) => {
      if (eventSource.readyState === EventSource.CLOSED && optionsRef.current.onError) {
        optionsRef.current.onError({ message: 'Bağlantı kapandı.' });
      }
    };

    return () => {
      eventSource.close();
      eventSourceRef.current = null;
    };
  }, [url]);

  return eventSourceRef.current;
}
