// Screen-space positions of clusters, written every frame by the scene and
// read by the DOM/SVG HUD (targeting ring, organic labels) without React.

export type ScreenCluster = {
  id: number;
  verdict: string;
  x: number;
  y: number;
  r: number;
  visible: boolean;
  depth: number;
};

type Listener = (list: ScreenCluster[]) => void;

export type Rect = { x0: number; y0: number; x1: number; y1: number };

class HudBus {
  list: ScreenCluster[] = [];
  /** screen rect of the target readout card, so labels can keep clear of it */
  readout: Rect | null = null;
  private listeners = new Set<Listener>();

  publish(list: ScreenCluster[]) {
    this.list = list;
    for (const l of this.listeners) l(list);
  }

  subscribe(l: Listener) {
    this.listeners.add(l);
    return () => {
      this.listeners.delete(l);
    };
  }

  get(id: number) {
    return this.list.find((c) => c.id === id);
  }
}

export const hudBus = new HudBus();
