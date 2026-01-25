# Sound Files

This directory contains sound files for the attendance system.

## Required Files:

### success.mp3

- **Purpose**: Played when a student successfully scans their barcode
- **Format**: MP3 audio file
- **Duration**: Short (1-2 seconds)
- **Suggestion**: A pleasant "ding" or "beep" sound

### error.mp3

- **Purpose**: Played when a barcode scan fails or is rejected
- **Format**: MP3 audio file
- **Duration**: Short (1-2 seconds)
- **Suggestion**: An "error" or "warning" sound

## How to Add Sound Files:

1. Obtain or create the sound files
2. Place them in this directory (`static/sounds/`)
3. Ensure they are named exactly `success.mp3` and `error.mp3`

## Free Sound Resources:

You can find free sound effects at:

- Freesound.org (https://freesound.org/)
- Zapsplat (https://www.zapsplat.com/)
- Pixabay Audio (https://pixabay.com/music/sound-effects/)

## Usage:

The sound files are used in the JavaScript code:

```javascript
const successSound = new Audio("/static/sounds/success.mp3");
const errorSound = new Audio("/static/sounds/error.mp3");

// Play success sound
successSound.play();

// Play error sound
errorSound.play();
```

Make sure to add these files before deploying the application.
