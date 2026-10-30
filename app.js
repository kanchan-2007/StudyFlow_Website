document.addEventListener("DOMContentLoaded", () => {
  const slides = Array.from(document.querySelectorAll(".slide"));
  const navLinks = Array.from(
    document.querySelectorAll(".top-navigation .nav-item[data-slide]")
  );

  if (!slides.length) return;

  const validIds = new Set(slides.map((slide) => slide.id));

  // Disable horizontal slide behaviour
  const track = document.getElementById("slideTrack");

  if (track) {
    track.style.transform = "none";
    track.style.transition = "none";
    track.style.width = "100%";
  }

  slides.forEach((slide) => {
    slide.style.flex = "none";
    slide.style.width = "100%";
    slide.style.height = "auto";
    slide.style.overflow = "visible";
    slide.removeAttribute("aria-hidden");
    slide.inert = false;
  });

  function setActiveNav(id) {
    navLinks.forEach((link) => {
      const active = link.dataset.slide === id;

      link.classList.toggle("active", active);

      if (active) {
        link.setAttribute("aria-current", "page");
      } else {
        link.removeAttribute("aria-current");
      }
    });
  }

  function goToSection(id, updateHash = true) {
    if (!validIds.has(id)) return;

    const section = document.getElementById(id);
    if (!section) return;

    setActiveNav(id);

    if (updateHash) {
      history.replaceState(null, "", `#${id}`);
    }

    section.scrollIntoView({
      behavior: "auto",
      block: "start"
    });

    try {
      sessionStorage.setItem("studyflow-active-slide", id);
    } catch (_) {}
  }

  // Navigation clicks
  navLinks.forEach((link) => {
    link.addEventListener("click", (event) => {
      const id = link.dataset.slide;

      if (!validIds.has(id)) return;

      event.preventDefault();
      goToSection(id);
    });
  });

  // Restore the requested section after Flask redirects
  const hashId = window.location.hash.slice(1);

  if (validIds.has(hashId)) {
    requestAnimationFrame(() => goToSection(hashId, false));
  } else {
    setActiveNav("home");
  }

  // Update active navigation while scrolling
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort(
            (a, b) =>
              b.intersectionRatio - a.intersectionRatio
          );

        if (visible.length) {
          setActiveNav(visible[0].target.id);
        }
      },
      {
        root: null,
        rootMargin: "-15% 0px -55% 0px",
        threshold: [0, 0.1, 0.25, 0.5]
      }
    );

    slides.forEach((slide) => observer.observe(slide));
  }

  // Flash messages
  document.querySelectorAll(".flash").forEach((item) => {
    setTimeout(() => {
      item.style.transition = "opacity .35s ease";
      item.style.opacity = "0";

      setTimeout(() => item.remove(), 380);
    }, 4200);
  });

  // Keyboard navigation: move vertically between sections
  document.addEventListener("keydown", (event) => {
    if (
      event.altKey ||
      event.ctrlKey ||
      event.metaKey ||
      ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(
        event.target?.tagName
      ) ||
      event.target?.isContentEditable
    ) {
      return;
    }

    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") {
      return;
    }

    const current = slides.findIndex(
      (slide) => slide.id === window.location.hash.slice(1)
    );

    const fallback = Math.max(
      0,
      slides.findIndex((slide) =>
        slide.getBoundingClientRect().top >= -20
      )
    );

    const index = current >= 0 ? current : fallback;

    if (event.key === "ArrowDown" && index < slides.length - 1) {
      event.preventDefault();
      goToSection(slides[index + 1].id);
    } else if (event.key === "ArrowUp" && index > 0) {
      event.preventDefault();
      goToSection(slides[index - 1].id);
    }
  });
});
