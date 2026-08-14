import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/* Auslieferung unter dem HA-Ingress: die Oberfläche liegt nicht unter einem festen Pfad,
   sondern unter /api/hassio_ingress/<token>/ — das Token wechselt je Sitzung. Deshalb
   `base: './'`: Vite erzeugt relative Verweise auf assets/…, die unter jedem Präfix
   auflösen. Ein führender Slash würde das Ingress-Präfix verlassen (docs/frontend.md).

   Dev-Proxy statt CORS: im Entwicklungsbetrieb dieselbe Origin wie in Produktion. Ziel ist
   der lokal laufende EP (EP_PORT, Default 8098). */
export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    outDir: 'dist',
    // Das Bündel wird mitcommittet (docs/frontend.md) — stabile Namen halten den Diff klein
    // und machen sichtbar, ob sich Inhalt oder nur ein Hash geändert hat.
    rollupOptions: {
      output: {
        entryFileNames: 'assets/app.js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name][extname]',
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5174,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8098', changeOrigin: true },
    },
  },
})
