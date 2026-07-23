// ─── Configuración del Torneo ───────────────────────────────────────────────
// Supabase (conexión directa desde GitHub Pages)
window.SUPABASE_URL  = 'https://jwkfihuidydpsaqkpucp.supabase.co';
window.SUPABASE_ANON = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp3a2ZpaHVpZHlkcHNhcWtwdWNwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ1Nzg3NTksImV4cCI6MjEwMDE1NDc1OX0.RKMDbvRnMzSstqfIu7vNc86zRKAWpAzgYW4NrU0HlAU';

// Backend Python (local o Railway/Render)
window.TOURNAMENT_API_BASE = window.TOURNAMENT_API_BASE
  || (location.hostname.endsWith('github.io')
    ? ''   // En GitHub Pages solo usamos Supabase directo
    : `${location.origin}/api`);
