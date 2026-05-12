import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';

const projects = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/projects" })
});

const cv = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/cv" })
});

export const collections = {
  projects,
  cv,
};
