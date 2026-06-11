/* ═══════════════════════════════════════════════════════
   AutoTrader — Onboarding Website JavaScript
   Animations, interactions, counters
   ═══════════════════════════════════════════════════════ */

// ═══ NAVBAR SCROLL ═══
const navbar = document.querySelector('.navbar');
window.addEventListener('scroll', () => {
  if (window.scrollY > 50) navbar.classList.add('scrolled');
  else navbar.classList.remove('scrolled');
});

// ═══ MOBILE MENU ═══
const hamburger = document.querySelector('.hamburger');
const mobileMenu = document.querySelector('.mobile-menu');
if (hamburger && mobileMenu) {
  hamburger.addEventListener('click', () => mobileMenu.classList.toggle('open'));
  mobileMenu.querySelectorAll('a').forEach(a => a.addEventListener('click', () => mobileMenu.classList.remove('open')));
}

// ═══ NUMBER COUNTER ANIMATION ═══
function animateCounter(el) {
  const target = parseInt(el.dataset.target) || 0;
  const prefix = el.dataset.prefix || '';
  const suffix = el.dataset.suffix || '';
  const duration = 1500;
  const start = performance.now();
  function update(now) {
    const elapsed = now - start;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = Math.floor(eased * target);
    el.textContent = prefix + current.toLocaleString('en-IN') + suffix;
    if (progress < 1) requestAnimationFrame(update);
  }
  requestAnimationFrame(update);
}

const counterObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting && !entry.target.dataset.animated) {
      entry.target.dataset.animated = 'true';
      animateCounter(entry.target);
    }
  });
}, { threshold: 0.5 });

document.querySelectorAll('[data-counter]').forEach(el => counterObserver.observe(el));

// ═══ TYPING EFFECT ═══
function typeText(el, text, speed = 50) {
  el.textContent = '';
  let i = 0;
  function type() {
    if (i < text.length) {
      el.textContent += text[i];
      i++;
      setTimeout(type, speed);
    }
  }
  type();
}

const typingEl = document.querySelector('[data-typing]');
if (typingEl) {
  const text = typingEl.dataset.typing;
  setTimeout(() => typeText(typingEl, text, 60), 500);
}

// ═══ CARD HOVER GLOW ═══
document.querySelectorAll('.card').forEach(card => {
  card.addEventListener('mouseenter', () => card.style.transform = 'translateY(-4px)');
  card.addEventListener('mouseleave', () => card.style.transform = 'translateY(0)');
});
