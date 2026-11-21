import { useCallback, useEffect, useRef, useState } from 'react';
import { SLIDE_HEIGHT, SLIDE_WIDTH } from '../presentationLayout';

export function usePresentationControls(totalSlides: number) {
  const [currentSlide, setCurrentSlide] = useState<number>(1);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [isGridOpen, setIsGridOpen] = useState<boolean>(false);
  const [isScrollMode, setIsScrollMode] = useState<boolean>(false);
  const [isNotesOpen, setIsNotesOpen] = useState<boolean>(false);
  const [isEvidenceOpen, setIsEvidenceOpen] = useState<boolean>(false);
  const [scale, setScale] = useState<number>(1);

  const stageContainerRef = useRef<HTMLDivElement | null>(null);
  const appRootRef = useRef<HTMLDivElement | null>(null);

  const goToSlide = useCallback((n: number) => {
    const clamped = Math.max(1, Math.min(totalSlides, n));
    setCurrentSlide(clamped);
    setIsGridOpen(false);
    setIsScrollMode(false);
  }, []);

  const nextSlide = useCallback(() => {
    setCurrentSlide((prev) => Math.min(totalSlides, prev + 1));
  }, []);

  const prevSlide = useCallback(() => {
    setCurrentSlide((prev) => Math.max(1, prev - 1));
  }, []);

  const toggleFullscreen = useCallback(async () => {
    try {
      if (!document.fullscreenElement) {
        await appRootRef.current?.requestFullscreen?.();
      } else {
        await document.exitFullscreen?.();
      }
    } catch {
      setIsFullscreen((prev) => !prev);
    }
  }, []);

  const handleExportPdf = useCallback(() => {
    setIsGridOpen(false);
    setIsEvidenceOpen(false);
    window.print();
  }, []);

  // Sync native fullscreen changes
  useEffect(() => {
    const onFsChange = () => {
      setIsFullscreen(Boolean(document.fullscreenElement));
    };
    document.addEventListener('fullscreenchange', onFsChange);
    return () => document.removeEventListener('fullscreenchange', onFsChange);
  }, []);

  // Proportional 16:9 scaling keeping clean space above floating dock
  useEffect(() => {
    const el = stageContainerRef.current;
    if (!el) return;

    const updateScale = () => {
      const rect = el.getBoundingClientRect();
      const padX = isFullscreen ? 20 : 32;
      const padY = isScrollMode ? 90 : isFullscreen ? 18 : 76;
      const availW = Math.max(320, rect.width - padX);
      const availH = Math.max(200, rect.height - padY);
      const nextScale = Math.min(availW / SLIDE_WIDTH, availH / SLIDE_HEIGHT);
      setScale(nextScale);
    };

    updateScale();
    const rafId = requestAnimationFrame(updateScale);
    const ro = new ResizeObserver(updateScale);
    ro.observe(el);
    window.addEventListener('resize', updateScale);
    return () => {
      cancelAnimationFrame(rafId);
      ro.disconnect();
      window.removeEventListener('resize', updateScale);
    };
  }, [isFullscreen, isScrollMode]);

  // Keyboard navigation
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
        return;
      }

      if (e.key === 'ArrowRight' || e.key === 'PageDown') {
        if (!isScrollMode) {
          e.preventDefault();
          nextSlide();
        }
      } else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
        if (!isScrollMode) {
          e.preventDefault();
          prevSlide();
        }
      } else if (e.key === ' ' && tag !== 'BUTTON' && !isScrollMode) {
        e.preventDefault();
        nextSlide();
      } else if (e.key === 'Home') {
        e.preventDefault();
        goToSlide(1);
      } else if (e.key === 'End') {
        e.preventDefault();
        goToSlide(totalSlides);
      } else if (e.key.toLowerCase() === 'f') {
        e.preventDefault();
        toggleFullscreen();
      } else if (e.key.toLowerCase() === 'n') {
        e.preventDefault();
        setIsNotesOpen((prev) => !prev);
      } else if (e.key === 'Escape') {
        setIsGridOpen(false);
        setIsEvidenceOpen(false);
        setIsNotesOpen(false);
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [goToSlide, isScrollMode, nextSlide, prevSlide, toggleFullscreen]);

  return { currentSlide, isFullscreen, isGridOpen, setIsGridOpen, isScrollMode, setIsScrollMode, isNotesOpen, setIsNotesOpen, isEvidenceOpen, setIsEvidenceOpen, scale, stageContainerRef, appRootRef, goToSlide, nextSlide, prevSlide, toggleFullscreen, handleExportPdf };
}
