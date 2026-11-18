"""
LOVE LETTER - a pink envelope is drawn in by light, a heart seal pops on,
the flap swings open, the seal floats up and beats, and a letter slides out
with a little message typed onto it.

    python letter.py                     open the animated window
    python letter.py --shot 11 out.png   render the frame at t=11s to a PNG (no window)

Keys: SPACE pause · R restart · S screenshot · ESC quit
Needs ../ascii_engine.py and:  pip install numpy pygame-ce

Change MESSAGE below to write your own letter.
"""
import math
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ascii_engine as E  # noqa: E402

E.SCREEN_CY = 540
E.CAM_D = 6.0
E.EDGE_T = 0.12
E.RAMPS = [".:-=+*cxvunoeaQ0&8B%$#@",      # 0: envelope
           " .,:;-~"]                       # 1: paper (kept faint so the writing stands out)

MESSAGE = [("my dear,", (200, 140, 160)),
           ("I  L O V E  Y O U", (255, 70, 120)),
           (E.HEART + "  always  " + E.HEART, (255, 150, 190))]

EW, EH = 2.4, 1.55          # envelope size
FLAP_D = 0.62 * EH          # how far the flap reaches down when closed
CARD_W, CARD_H = 0.9 * EW, 0.95 * EH
LIFT = 0.72 * EH            # how far the letter slides out
T_DRAW = 2.5
T_SEAL = 2.6
T_OPEN0, T_OPEN1 = 3.8, 5.4
T_RISE0, T_RISE1 = 5.0, 7.5
T_TYPE = 8.0
PINKS = [(255, 110, 160), (255, 60, 110), (255, 190, 215), (255, 255, 255)]


def plane(x0, x1, y0, y1, z, nu, nv):
    u = np.linspace(x0, x1, nu)[:, None]
    v = np.linspace(y0, y1, nv)[None, :]
    P = np.stack([u * np.ones_like(v), v * np.ones_like(u), np.full((nu, nv), z)], -1)
    return P, np.broadcast_to(np.array([0, 0, -1.0]), P.shape)


def seg_dist(P, a, b):
    a, b = np.asarray(a), np.asarray(b)
    ab = b - a
    t = np.clip(np.sum((P - a) * ab, -1) / np.dot(ab, ab), 0, 1)
    return np.linalg.norm(P - (a + t[..., None] * ab), axis=-1)


FRONT_P, FRONT_N = plane(-EW / 2, EW / 2, -EH / 2, EH / 2, -0.03, 170, 110)
_fold = np.minimum(seg_dist(FRONT_P[..., :2], [-EW / 2, -EH / 2], [0, 0.04]),
                   seg_dist(FRONT_P[..., :2], [EW / 2, -EH / 2], [0, 0.04]))
FRONT_COL = np.where((_fold < 0.035)[..., None], np.array([170, 60, 110]), np.array([245, 115, 165]))
FRONT_GAIN = np.where(_fold < 0.035, 0.38, 0.62 + 0.12 * (FRONT_P[..., 1] / EH))
CARD_Z = 0.10               # the paper sits a little behind the front of the envelope
CARD_P0, CARD_N = plane(-CARD_W / 2, CARD_W / 2, -CARD_H / 2, CARD_H / 2, CARD_Z, 150, 100)
SEAL_P, SEAL_N, _, SEAL_PH = E.puffy_heart(scale=1.0, depth=0.4, nt=120, nphi=20)
_m = np.abs(np.sin(SEAL_PH))[..., None]
SEAL_COL = np.array([200, 15, 50]) * (1 - _m) + np.array([255, 90, 120]) * _m


def flap(a):
    """The triangular flap, hinged on the top edge. a = 0 closed ... pi fully open."""
    u = np.linspace(0, 1, 60)[:, None]
    v = np.linspace(-1, 1, 120)[None, :]
    x = v * (1 - u) * EW / 2
    zh = 0.18 - 0.225 * (1 - a / math.pi)        # in front when closed, behind the paper when open
    y = EH / 2 - u * FLAP_D * math.cos(a)
    z = zh - u * FLAP_D * math.sin(a)
    P = np.stack([x, y * np.ones_like(x), z * np.ones_like(x)], -1)
    edge = (np.abs(v) > 0.95) & (u < 0.97) * np.ones_like(x, bool)       # crease along the two edges
    gain = np.where(edge, 0.45, 0.85)
    return P, E.surface_normals(P), gain


class Letter:
    title = "LOVE LETTER - ASCII"

    def __init__(self):
        self.rng = random.Random(14)
        self.reset()

    def reset(self):
        self.t = 0.0
        self.fx = E.Particles(self.rng)
        self.floaters = E.Particles(self.rng)
        self.float_timer = 0.0
        self.burst_done = False
        self.pop_done = False
        for _ in range(22):
            self._floater(y=self.rng.uniform(-3, 3))

    def _floater(self, y=-3.3):
        r = self.rng
        self.floaters.emit([r.uniform(-4.2, 4.2), y, r.uniform(-0.5, 2.5)], n=1,
                           vel=[0, r.uniform(0.25, 0.45), 0], life=(9, 14), rgb=r.choice(PINKS),
                           chars=r.choice([E.HEART, E.HEART_O]), gravity=0.0, drag=1.0, wobble=0.5)

    # -- state -----------------------------------------------------------------
    def world(self):
        t = self.t
        return E.rot_y(0.22 * math.sin(t * 0.4)) @ E.rot_x(0.05 * math.sin(t * 0.6) - 0.05)

    def offset(self):
        return np.array([0, 0.04 * math.sin(self.t * 1.1), 0])

    def flap_angle(self):
        return math.pi * E.sstep(T_OPEN0, T_OPEN1, self.t)

    def lift(self):
        return LIFT * E.sstep(T_RISE0, T_RISE1, self.t)

    def seal(self):
        """Seal position (envelope space) and scale, or None."""
        t = self.t
        if t < T_SEAL:
            return None
        k = E.sstep(T_SEAL, T_SEAL + 0.5, t)
        pop = 0.24 * (k + 0.35 * math.sin(math.pi * k) * (1 - k))
        closed = np.array([0, EH / 2 - FLAP_D + 0.16, -0.09])
        hover = np.array([0.95, LIFT + CARD_H / 2 - 0.05, -0.45])
        f = E.sstep(T_OPEN0 - 0.2, T_OPEN0 + 1.6, t)
        pos = closed * (1 - f) + hover * f + np.array([0, 0.25 * math.sin(math.pi * f), -0.2 * math.sin(math.pi * f)])
        size = pop * (1 + 0.5 * f)
        if t > T_RISE1:
            ph = ((t - T_RISE1) * 1.1) % 1.0
            size *= 1 + 0.08 * (math.exp(-(ph / 0.06) ** 2) + 0.6 * math.exp(-((ph - 0.25) / 0.06) ** 2))
            pos = pos + np.array([0, 0.05 * math.sin(t * 1.4), 0])
        return pos, size

    def to_world(self, P):
        return P @ self.world().T + self.offset()

    def update(self, dt):
        t = self.t
        if t < T_DRAW + 0.1:
            x = -EW / 2 + EW * E.sstep(0, T_DRAW, t)
            self.fx.emit(self.to_world(np.array([x, 0.6 * math.sin(t * 7), -0.1])), n=3, spread=0.4,
                         up=0.1, life=(0.4, 0.9), rgb=(255, 210, 225), chars="*+.", gravity=-0.8)
        if not self.pop_done and t >= T_SEAL + 0.25:
            self.pop_done = True
            pos, _ = self.seal()
            self.fx.emit(self.to_world(pos), n=14, spread=0.8, up=0.3, life=(0.5, 1.1),
                         rgb=(255, 200, 220), chars="*+.", gravity=-0.6)
        if not self.burst_done and t >= T_RISE1:
            self.burst_done = True
            for _ in range(26):
                p = np.array([self.rng.uniform(-CARD_W / 2, CARD_W / 2), self.lift() + CARD_H / 2, -0.05])
                self.fx.emit(self.to_world(p), n=1, vel=[self.rng.uniform(-.6, .6), self.rng.uniform(.6, 1.3),
                                                        self.rng.uniform(-.5, .1)],
                             life=(1.2, 2.2), rgb=self.rng.choice(PINKS), chars=E.HEART + E.HEART + "•.",
                             gravity=-0.25, drag=0.97)
        self.float_timer -= dt
        if self.float_timer <= 0:
            self.float_timer = 0.4
            self._floater()
        self.fx.update(dt)
        self.floaters.update(dt)
        self.t += dt

    # -- drawing -----------------------------------------------------------------
    def render(self, R, screen, stars):
        t = self.t
        cam = E.rot_x(0.08)
        Wm = self.world()
        off = self.offset()
        R.begin(screen, stars, t)
        sweep = -EW / 2 + (EW + 0.05) * E.sstep(0, T_DRAW, t)

        b = E.Batch()
        b.add(self.to_world(FRONT_P), FRONT_N @ Wm.T, FRONT_COL, spec=0.2, gain=FRONT_GAIN,
              mask=FRONT_P[..., 0] <= sweep)
        P, N, fg = flap(self.flap_angle())
        b.add(self.to_world(P), N @ Wm.T, (255, 160, 200), spec=0.25, gain=fg, mask=P[..., 0] <= sweep)
        lift = self.lift()
        if t > T_RISE0 - 0.5:
            card = CARD_P0 + np.array([0, lift - 0.02, 0])
            b.add(self.to_world(card), CARD_N @ Wm.T, (255, 245, 232), spec=0.0, gain=0.55, ramp=1)
        seal = self.seal()
        if seal is not None:
            pos, size = seal
            b.add(self.to_world(SEAL_P * size + pos), SEAL_N @ Wm.T, SEAL_COL, spec=0.5, gain=1.1)
        R.render_batch(b, cam, [((-0.5, 0.7, -0.75), 0.95, 22), ((0.6, 0.2, -0.6), 0.35, 40),
                                ((0.3, -0.4, 0.9), 0.25, 8)], ambient=0.2)
        if t > T_TYPE:
            self.type_message(R, cam, lift)
        R.draw_grid()
        R.draw_reflection(R.ground_row(cam, -EH / 2 - 0.15), n=8, strength=0.15)

        self.floaters.draw(R, cam, fade_in=1.5)
        self.fx.draw(R, cam)
        if t < T_DRAW + 0.1:
            x, y = R.cell_of(self.to_world(np.array([sweep, 0.6 * math.sin(t * 7), -0.1])) @ cam.T)
            R.draw_flare(R.layer, x, y, 3, (255, 225, 235), 1.0)
        if t > T_RISE1 and seal is not None:
            x, y = R.cell_of(self.to_world(seal[0] + [0, seal[1] * 0.8, 0]) @ cam.T)
            R.draw_rays(R.layer, x, y, t, (255, 190, 210), 0.5, n=7, length=5, spread=70)

        R.finish(screen)
        R.hud(screen, ["LOVE LETTER  .  2026",
                       f"flap {math.degrees(self.flap_angle()):5.1f}°   letter {lift / LIFT * 100:5.1f}%",
                       f"letters {R.letters:,}"], t)

    def type_message(self, R, cam, lift):
        """Type the message onto the paper, one character at a time. Each line is
        centred on a point of the paper and written straight into the character grid."""
        shown = int((self.t - T_TYPE) * 12)
        top = lift - 0.02 + CARD_H / 2 - 0.2
        for j, (line, col) in enumerate(MESSAGE):
            p = self.to_world(np.array([0, top - j * 0.17, CARD_Z])) @ cam.T
            sx, sy, _ = R.project(p[None])
            r = int(sy[0] // R.ch)
            c0 = int(sx[0] // R.cw) - len(line) // 2
            for i, ch in enumerate(line[:max(0, shown)]):
                c = c0 + i
                if 0 <= r < R.rows and 0 <= c < R.cols and R.occ[r, c]:
                    R.chars[r, c] = ch
                    R.colors[r, c] = col if ch != " " else (0, 0, 0)
            shown -= len(line)


if __name__ == "__main__":
    E.run(Letter(), E.Starfield(random.Random(6), n=260, flares=7, flare_size=(2, 5), flare_a=0.55),
          prefix="letter")
