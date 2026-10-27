# Audio / picture sync check (video/scouts_eye_demo.mp4)

Measured from the finished video (110.6 s), not from a recording log (`python video/check_sync.py`): every 0.2 s of the demo part (7–98 s) a frame is read with Apple's Vision text recognition, the active tab is taken from the colour of its button, and the start and end of every narration segment are measured from the video's audio track. An event is OK when it first becomes visible inside its narration segment (or up to 1 s before it).

| screen event | first visible (s) | visible until (s) | narration segment | segment (s) | speech measured (s) | result |
|---|---|---|---|---|---|---|
| match tab: the 2' goal as a fact card on the stage | 10.0 | 13.8 | 2 | 8–20 | 8.1–18.9 | OK |
| match tab, Fan + Analyst: two verified texts side by side | 20.0 | 33.8 | 3 | 20–34 | 20.1–31.1 | OK |
| evidence panel: a supported claim rule | 34.0 | 49.8 | 4 | 34–50 | 34.1–44.2 | OK |
| agent trace tab: the selected overlay's agents, pre-check and repair | 50.0 | 67.8 | 5 | 50–68 | 50.2–66.5 | OK |
| match tab: the player-focus text about Petrovic on the stage | 68.0 | 74.8 | 6 | 68–82 | 68.2–80.5 | OK |
| player profile tab: Petrovic's profile with the line 'Before M12' | 75.0 | 81.8 | 6 | 68–82 | 68.2–80.5 | OK |
| match tab: the 49' penalty goal as a fact card | 85.0 | 87.8 | 7 | 82–98 | 82.2–94.7 | OK |
| match tab: the verified 49' texts | 88.0 | 92.8 | 7 | 82–98 | 82.2–94.7 | OK |
| recap tab: the fan recap in English | 93.0 | 97.8 | 7 | 82–98 | 82.2–94.7 | OK |

Result: **9 / 9** screen events visible inside their narration segment.

| segment | slot (s) | narration audio (s) | speech measured in the video (s) | fits in its slot |
|---|---|---|---|---|
| 1 | 0–8 | 6.12 | 0.1–5.8 | yes |
| 2 | 8–20 | 11.38 | 8.1–18.9 | yes |
| 3 | 20–34 | 11.47 | 20.1–31.1 | yes |
| 4 | 34–50 | 10.66 | 34.1–44.2 | yes |
| 5 | 50–68 | 16.8 | 50.2–66.5 | yes |
| 6 | 68–82 | 12.91 | 68.2–80.5 | yes |
| 7 | 82–98 | 13.06 | 82.2–94.7 | yes |
| 8 | 98–112 | 12.6 | 98.1–110.2 | yes |

Author name (Laczkovics Martin) on the opener / closer / cover: yes / yes / yes.

One frame per event (taken while the event is visible and its narration is spoken): `video_frames/ (outside the repository)`, listed in `frames.md` there.
