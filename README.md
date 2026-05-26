# 6 Ascii Moon Frontend Template

An experimental lunar observatory website template with a split hero layout, flowing interactive ASCII moon field, manifesto video section, facilities directory with detail pages, live observation feed, archive carousel, and monochrome footer.

## Features

- Split hero with editorial text panel on the left and interactive ASCII moon field on the right
- Hero title styled with local `Geist Pixel` line variant
- Manifesto section with left video and right editorial text
- Facilities directory with four-column layout and per-facility detail pages
- Live observation section with video, status line, and dynamic coordinates
- 3D archive carousel with fullscreen preview overlay
- Monochrome footer and overall observatory UI language

## Tech Stack

- React 19 + TypeScript + Vite
- React Router
- Tailwind CSS v3
- GSAP + ScrollTrigger
- Geist font package

## Quick Start

1. Install dependencies: `npm install`
2. Edit `src/config.ts`
3. Add images to `public/images/`
4. Add videos to `public/videos/`
5. Run the dev server: `npm run dev`
6. Build for production: `npm run build`

## Configuration

All editable content is defined in `src/config.ts`. Do not modify the ASCII field logic or section interaction logic unless you are fixing a real bug.

### `siteConfig`

```ts
export const siteConfig = {
  language: "",
  siteTitle: "",
  siteDescription: "",
}
```

### `navigationConfig`

```ts
export const navigationConfig = {
  brandName: "",
  links: [
    // { label: "", href: "#archives" }
  ],
}
```

### `heroConfig`

```ts
export const heroConfig = {
  eyebrow: "",
  titleLines: [],
  leadText: "",
  supportingNotes: [],
}
```

### `manifestoConfig`

```ts
export const manifestoConfig = {
  videoPath: "",
  text: "",
}
```

### `facilitiesConfig`

```ts
export const facilitiesConfig = {
  sectionLabel: "",
  detailBackText: "",
  detailNotFoundText: "",
  detailReturnText: "",
  items: [
    {
      slug: "",
      name: "",
      code: "",
      address: "",
      status: "",
      email: "",
      phone: "",
      ctaText: "",
      ctaHref: "",
      image: "",
      utcOffset: 0,
      article: {
        title: "",
        paragraphs: [],
      },
    },
  ],
}
```

### `observationConfig`

```ts
export const observationConfig = {
  sectionLabel: "",
  videoPath: "",
  statusText: "",
  latLabel: "",
  lonLabel: "",
  initialLat: 0,
  initialLon: 0,
}
```

### `archivesConfig`

```ts
export const archivesConfig = {
  sectionLabel: "",
  vaultTitle: "",
  closeText: "",
  items: [
    {
      src: "",
      label: "",
    },
  ],
}
```

### `footerConfig`

```ts
export const footerConfig = {
  copyrightText: "",
  statusText: "",
}
```

## Required Images

Place all images in `public/images/`.

If the required image assets do not already exist, write image-generation prompts based on the user's request and this template's visual style, call the `generate_image` tool, save the generated files into `public/images/`, and then reference those final file paths in `src/config.ts`.

### Facilities Directory

- One image per facility item in `facilitiesConfig.items`
- Recommended ratio: portrait, ideally 3:4
- Recommended minimum size: 1200 x 1600
- High-contrast monochrome or heavily desaturated imagery works best

### Archives

- One image per archive item in `archivesConfig.items`
- Recommended ratio: portrait or near-portrait
- Recommended minimum size: 1200px on the short edge
- Images should hold up under grayscale display

## Required Videos

Place all videos in `public/videos/`.

If the required video assets do not already exist, write video-generation prompts based on the user's request and this template's visual style, call the `generate_video` tool, save the generated files into `public/videos/`, and then reference those final file paths in `src/config.ts`.

### Manifesto Video

- One video used by `manifestoConfig.videoPath`
- Recommended ratio: 16:9

### Observation Feed Video

- One video used by `observationConfig.videoPath`
- Recommended ratio: 16:9

## Design

**Colors**

- Primary hero and archive sections: black
- Content sections: white / off-white
- Typography is monochrome with no accent color system

**Fonts**

- Hero title: `Geist Pixel` line variant
- UI and body text: `IBM Plex Mono`
- ASCII field: `Fragment Mono`

**Motion**

- Interactive ASCII moon field in hero
- Scroll-triggered manifesto reveal
- Facilities column reveal on scroll
- Observation video reveal
- 3D archive carousel and preview burst animation

## Notes

- Empty config values hide the relevant section or element
- `heroConfig.supportingNotes` works best with exactly 3 items for the current staggered composition
- `facilitiesConfig.items` powers both the facilities grid and the facility detail pages
- Facility detail routes rely on client-side routing, so static hosting should support SPA fallback to `index.html`
