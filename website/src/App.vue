<template>
  <RouterView />
</template>

<script setup lang="ts">
</script>

<style>
/* ── Global Reset & Fonts ── */
@import url('https://fonts.googleapis.com/css2?family=Fredoka:wght@400;500;600;700&family=Nunito:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html {
  scroll-behavior: smooth;
}

body {
  font-family: 'Nunito', -apple-system, sans-serif;
  background: #fffbf5;
  color: #3d2c24;
  -webkit-font-smoothing: antialiased;
}
</style>
