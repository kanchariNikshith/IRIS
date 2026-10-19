"""Small Qt-painted orb; all geometry uses Qt device-independent pixels."""
import math
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal, QVariantAnimation, QTimer, QElapsedTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen, QRadialGradient, QLinearGradient
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from iris.ui.theme import COLORS, STATES, stylesheet


def constrain_position(point: QPoint, size: int, areas: list[QRect]) -> QPoint:
    if not areas:
        return point
    center = point + QPoint(size // 2, size // 2)
    area = next((a for a in areas if a.contains(center)), None)
    if area is None:
        area = min(areas, key=lambda a: (a.center() - center).manhattanLength())
    return QPoint(max(area.left(), min(point.x(), max(area.left(), area.right() - size + 1))),
                  max(area.top(), min(point.y(), max(area.top(), area.bottom() - size + 1))))


class OrbFace(QWidget):
    def __init__(self, parent=None, *, diameter=120, label=True):
        super().__init__(parent)
        self.setFixedSize(diameter, diameter)
        self.state = "idle"
        self.last_message = "Click to open IRIS. Use Mic or Ctrl+Alt+Space to speak."
        self.show_label = label
        self.reduced_motion = False
        self._accent = QColor(STATES["idle"][0])
        self._halo = QColor(STATES["idle"][1])
        self._pulse = 0.0
        self._orbit_angle = 0.0
        self._orbit_clock = QElapsedTimer()
        self._orbit_timer = QTimer(self)
        self._orbit_timer.setInterval(33)
        self._orbit_timer.timeout.connect(self._orbit_frame)
        self._fade = QVariantAnimation(self)
        self._fade.setDuration(150)
        self._fade.valueChanged.connect(self._fade_frame)
        self._motion = QVariantAnimation(self)
        self._motion.setStartValue(0.0)
        self._motion.setEndValue(1.0)
        self._motion.valueChanged.connect(self._pulse_frame)
        self.setAccessibleName("IRIS orb")

    @property
    def microphone_active(self):
        return self.state == "listening"

    def _fade_frame(self, value):
        t = float(value)
        def mix(a, b):
            return QColor(*(round(x + (y - x) * t) for x, y in zip(a.getRgb(), b.getRgb())))
        self._accent = mix(self._old_accent, self._new_accent)
        self._halo = mix(self._old_halo, self._new_halo)
        self.update()

    def _pulse_frame(self, value):
        self._pulse = 4 * math.sin(math.pi * float(value)) ** 2
        self.update()

    def _orbit_frame(self):
        elapsed = self._orbit_clock.restart() / 1000.0
        speed = {"idle": 12, "listening": 20, "processing": 38,
                 "speaking": 18, "error": 8}.get(self.state, 0)
        self._orbit_angle = (self._orbit_angle + speed * min(elapsed, 0.1)) % 360
        self.update()

    def _sync_orbit(self):
        if self.isVisible() and not self.reduced_motion and self.state != "paused":
            self._orbit_clock.start()
            self._orbit_timer.start()
        else:
            self._orbit_timer.stop()

    def set_state(self, state):
        state = "processing" if state == "thinking" else state
        if state not in STATES:
            return
        self._fade.stop()
        self._motion.stop()
        self.state = state
        self._pulse = 0
        self._old_accent, self._old_halo = QColor(self._accent), QColor(self._halo)
        self._new_accent, self._new_halo = map(QColor, STATES[state][:2])
        self.setToolTip(f"IRIS — {state}" + (" — microphone open" if self.microphone_active else "") + "\n" + self.last_message)
        self.setAccessibleDescription(self.toolTip())
        if self.reduced_motion or not self.isVisible():
            self._accent, self._halo = self._new_accent, self._new_halo
        else:
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.start()
            durations = {"idle": 2500, "listening": 1200, "processing": 800, "speaking": 2000, "error": 450}
            if state in durations:
                self._motion.setDuration(durations[state])
                self._motion.setLoopCount(1 if state == "error" else -1)
                self._motion.start()
        self.update()
        self._sync_orbit()

    def set_reduced_motion(self, enabled):
        self.reduced_motion = bool(enabled)
        self.set_state(self.state)

    def showEvent(self, event):
        super().showEvent(event)
        self.set_state(self.state)

    def hideEvent(self, event):
        self._orbit_timer.stop()
        self._motion.stop()
        self._fade.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(self.width() / 120, self.height() / 120)
        center = QPointF(60, 60)
        radius = 56 if self.reduced_motion or self.state == "paused" else 52 + self._pulse
        gradient = QRadialGradient(center, radius)
        inner = QColor(self._halo)
        inner.setAlpha(230)
        gradient.setColorAt(0, inner)
        gradient.setColorAt(0.7, self._halo)
        outer = QColor(self._halo)
        outer.setAlpha(0)
        gradient.setColorAt(1, outer)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(gradient)
        p.drawEllipse(center, radius, radius)
        # A shaded glass sphere, with the light above-left and a dark lower rim.
        sphere = QRadialGradient(center, 50, QPointF(41, 32))
        sphere.setColorAt(0, QColor("#255968"))
        sphere.setColorAt(0.38, QColor("#0C2935"))
        sphere.setColorAt(0.8, QColor("#04131D"))
        sphere.setColorAt(1, QColor("#01060D"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(sphere)
        p.drawEllipse(center, 50, 50)
        p.setBrush(Qt.BrushStyle.NoBrush)
        # Segmented beveled rings, fine radial ticks and amber instrumentation.
        p.save()
        p.translate(center)
        p.rotate(self._orbit_angle)
        p.translate(-center)
        rim = QLinearGradient(22, 15, 95, 110)
        rim.setColorAt(0, QColor("#E0FFFF"))
        rim.setColorAt(0.28, self._accent.lighter(150))
        rim.setColorAt(0.62, self._accent.darker(160))
        rim.setColorAt(1, self._accent.lighter(125))
        for radius, width in ((49, 2.4), (34, 2.7)):
            pen = QPen(rim, width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            if self.state == "paused":
                pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            rect = QRectF(60-radius, 60-radius, radius*2, radius*2)
            for start, span in ((7, 79), (96, 74), (185, 78), (275, 72)):
                p.drawArc(rect, start*16, span*16)
        p.setPen(QPen(self._accent.darker(190), 0.6))
        p.drawEllipse(center, 46, 46)
        p.drawEllipse(center, 29, 29)
        for i in range(60):
            a = math.radians(i * 6)
            outer_radius = 44
            inner_radius = 40 if i % 5 == 0 else 42
            color = self._accent.lighter(135) if i % 5 == 0 else self._accent.darker(130)
            p.setPen(QPen(color, 0.75 if i % 5 == 0 else 0.45))
            p.drawLine(QPointF(60 + inner_radius*math.cos(a), 60 + inner_radius*math.sin(a)),
                       QPointF(60 + outer_radius*math.cos(a), 60 + outer_radius*math.sin(a)))
        p.setPen(QPen(self._accent.darker(170), 0.5))
        for i in range(40):
            a = math.radians(i * 9)
            p.drawLine(QPointF(60 + 35.5*math.cos(a), 60 + 35.5*math.sin(a)),
                       QPointF(60 + 37*math.cos(a), 60 + 37*math.sin(a)))
        p.setPen(QPen(self._accent, 5))
        p.drawArc(QRectF(22, 22, 76, 76), -48*16, 132*16)
        p.setPen(QPen(QColor("#FFC857"), 1.4))
        p.drawArc(QRectF(22, 22, 76, 76), 144*16, 53*16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#FFD56A"))
        for x, y in ((48, 23), (55, 21.5), (62, 21.5)):
            p.drawEllipse(QPointF(x, y), 0.9, 0.9)
        p.restore()
        # Tilted orbital paths and glowing satellites give depth around the core.
        p.save()
        p.translate(center)
        p.rotate(-28)
        path_color = QColor(self._accent)
        path_color.setAlpha(100)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(path_color, 0.65))
        p.drawEllipse(QRectF(-55, -20, 110, 40))
        p.rotate(56)
        p.drawEllipse(QRectF(-55, -20, 110, 40))
        for offset, direction in ((0, 1), (180, -1)):
            angle = math.radians(self._orbit_angle * direction + offset)
            satellite = QPointF(55 * math.cos(angle), 20 * math.sin(angle))
            glow = QRadialGradient(satellite, 4)
            glow.setColorAt(0, QColor("#E8FFFF"))
            glow.setColorAt(0.35, self._accent)
            glow.setColorAt(1, QColor(0, 0, 0, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(satellite, 4, 4)
        p.restore()
        # Curved specular highlight supplies depth without a GPU or spin timer.
        sheen = QRadialGradient(QPointF(43, 30), 37)
        sheen.setColorAt(0, QColor(195, 255, 255, 50))
        sheen.setColorAt(1, QColor(195, 255, 255, 0))
        p.setBrush(sheen)
        p.drawEllipse(center, 48, 48)
        if self.show_label:
            p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            p.setPen(QPen(self._accent.darker(170), 1))
            p.drawText(QRectF(22, 51.5, 76, 20), Qt.AlignmentFlag.AlignCenter, "I.R.I.S.")
            p.setPen(QColor("#E8FFFF"))
            p.drawText(QRectF(22, 50, 76, 20), Qt.AlignmentFlag.AlignCenter, "I.R.I.S.")
        if self.microphone_active:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(COLORS["mic"]))
            p.drawEllipse(QPointF(103, 12), 5, 5)
        p.end()


class FloatingOrb(OrbFace):
    clicked = Signal()
    toggle_window = Signal()
    toggle_pause = Signal()
    quit_requested = Signal()
    motion_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(stylesheet())
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._press = None
        self._dragged = False
        self.menu = QMenu(self)
        self.menu.addAction("Show or hide IRIS", self.toggle_window.emit)
        self.pause_action = self.menu.addAction("Pause listening", self.toggle_pause.emit)
        motion = self.menu.addAction("Reduce motion")
        motion.setCheckable(True)
        motion.toggled.connect(self.motion_changed.emit)
        self.menu.addSeparator()
        self.menu.addAction("Exit IRIS", self.quit_requested.emit)
        app = QGuiApplication.instance()
        app.screenAdded.connect(self._screen_added)
        app.screenRemoved.connect(self.reclamp)
        for screen in app.screens():
            self._watch_screen(screen)
        area = app.primaryScreen().availableGeometry()
        self.move(area.right() - 32 - 120 + 1, area.bottom() - 110 - 120 + 1)
        self.reclamp()

    def _watch_screen(self, screen):
        screen.availableGeometryChanged.connect(self.reclamp)
        screen.geometryChanged.connect(self.reclamp)

    def _screen_added(self, screen):
        self._watch_screen(screen)
        self.reclamp()

    def reclamp(self, *args):
        areas = [screen.availableGeometry() for screen in QGuiApplication.screens()]
        self.move(constrain_position(self.pos(), self.width(), areas))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.globalPosition().toPoint()
            self._start_pos = self.pos()
            self._dragged = False
            event.accept()

    def mouseMoveEvent(self, event):
        if self._press is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._press
            if delta.manhattanLength() >= QApplication.startDragDistance():
                self._dragged = True
            if self._dragged:
                self.move(self._start_pos + delta)
                self.reclamp()
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._press is not None:
            click = not self._dragged
            self._press = None
            if click:
                self.clicked.emit()
            event.accept()

    def contextMenuEvent(self, event):
        self.pause_action.setText("Resume listening" if self.state == "paused" else "Pause listening")
        self.menu.popup(event.globalPos())
