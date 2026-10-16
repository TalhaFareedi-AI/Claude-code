---
name: scientific-plotter
description: Writes and runs scientific plot specifications for waveforms, signal spectra, and research curves in the sandbox. Use when the user asks for waveforms, FFT frequency spectra, signal plots, probability distributions, or training curves.
---
1. Identify the mathematical signal, spectrum, or scientific curve requested (e.g., sine wave + FFT spectrum, damped harmonic oscillator, normal distribution, or training loss curve).
2. State the exact formula in LaTeX (`$$ ... $$`) and work through Input -> Step -> Output for one representative point.
3. Emit a ```science_plot fenced JSON block specifying `kind`, `title`, `x_label`, `y_label`, and parameters.
4. Every generated scientific figure carries the "Computed plot" badge.
