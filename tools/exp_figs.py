"""Plotly figures for the «📈 Πειράματα» tab (M-20261021-008), drawn on the fly from result/live JSON (no stored images).
Layouts follow the DInos paper (docs/papers/dinos_dexa_paper2025.pdf): Fig.5 checkpoint bars, Fig.6 2x2 metrics over
time with the number of VMs on the right axis, Fig.7 total reward bars."""
import plotly.graph_objects as go
from plotly.subplots import make_subplots

GREEN, PURPLE, BLUE, RED, ORANGE, GREY = "#008000", "#800080", "#1f3fd6", "#e00000", "#f2a000", "#898781"
GRID = "rgba(137,135,129,0.25)"


def _base(fig, height, title=None):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40 if title else 10, b=30), title=title,
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", y=-0.18), hovermode="x unified")
    fig.update_xaxes(gridcolor=GRID)
    fig.update_yaxes(gridcolor=GRID)
    return fig


def _segments(ts, phases):
    """Contiguous (phase, t0, t1) runs."""
    out = []
    for t, p in zip(ts, phases):
        if out and out[-1][0] == p:
            out[-1][2] = t
        else:
            out.append([p, t, t])
    return out


def live_figure(cols, height=360, fit=None, spike=None, show_actual=True):
    """Load (left axis) and pods / pending pods (right axis) over the last ticks; eval segments shaded."""
    t = cols.get("t", [])
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    if show_actual or not fit:
        fig.add_trace(go.Scatter(x=t, y=cols.get("load"), name="load (είσοδος)", mode="lines",
                                 line=dict(color=BLUE, width=1.6)), secondary_y=False)
    if fit:
        fig.add_trace(go.Scatter(x=t, y=fit, name="σχεδιασμένο ημίτονο (χωρίς θόρυβο/spike)", mode="lines",
                                 line=dict(color=GREEN, width=1.6, dash="dash")), secondary_y=False)
    fig.add_trace(go.Scatter(x=t, y=cols.get("pods"), name="pods", mode="lines", line=dict(color=RED, width=2, shape="hv")),
                  secondary_y=True)
    if any(cols.get("pending") or []):
        fig.add_trace(go.Scatter(x=t, y=cols.get("pending"), name="pending pods", mode="lines",
                                 line=dict(color=ORANGE, width=1.2, dash="dot", shape="hv")), secondary_y=True)
    for ph, a, b in _segments(t, cols.get("phase", [])):
        if ph == "eval":
            fig.add_vrect(x0=a, x1=b, fillcolor=GREY, opacity=0.12, line_width=0)
    for ph, a, b in _segments(t, [bool(x) for x in spike or []]):
        if ph:
            fig.add_vrect(x0=a, x1=b, fillcolor=ORANGE, opacity=0.25, line_width=0,
                          annotation_text="spike", annotation_position="top left")
    fig.update_yaxes(title_text="load", secondary_y=False)
    fig.update_yaxes(title_text="pods", secondary_y=True, rangemode="tozero", showgrid=False)
    fig.update_xaxes(title_text="tick")
    return _base(fig, height)


def checkpoint_bars(panels, height=360):
    """Fig.5 analogue. panels: [(title, [(x label, value or None)], colour)] -> one bar subplot per panel."""
    fig = make_subplots(rows=1, cols=len(panels), subplot_titles=[p[0] for p in panels])
    for i, (_, bars, colour) in enumerate(panels, 1):
        xs = [b[0] for b in bars]
        ys = [b[1] for b in bars]
        fig.add_trace(go.Bar(x=xs, y=ys, marker_color=colour, showlegend=False,
                             text=[f"{v:,.0f}" if v is not None else "" for v in ys], textposition="outside"), row=1, col=i)
        fig.update_yaxes(title_text="Total Accumulated Reward" if i == 1 else None, row=1, col=i)
    fig.update_xaxes(tickangle=-35)
    return _base(fig, height).update_layout(hovermode="closest")


def metrics_over_time(ep, height=640):
    """Fig.6 analogue for one recorded episode: Load / Memory / CPU / Latency over time, number of VMs (pods) on the
    right axis as red dots."""
    n = len(ep.get("load", []))
    x = list(range(1, n + 1))
    panels = (("load", "Load Over Time", "Load", BLUE), ("mem", "Memory Usage Over Time", "Memory Usage", GREEN),
              ("cpu", "CPU Usage Over Time", "CPU Usage", ORANGE), ("latency", "Latency Over Time", "Latency", PURPLE))
    fig = make_subplots(rows=2, cols=2, subplot_titles=[p[1] for p in panels],
                        specs=[[{"secondary_y": True}, {"secondary_y": True}], [{"secondary_y": True}, {"secondary_y": True}]],
                        vertical_spacing=0.14, horizontal_spacing=0.12)
    for i, (k, _, ylab, colour) in enumerate(panels):
        r, c = i // 2 + 1, i % 2 + 1
        fig.add_trace(go.Scatter(x=x, y=ep.get(k), mode="lines", line=dict(color=colour, width=1), name=ylab,
                                 showlegend=False), row=r, col=c, secondary_y=False)
        fig.add_trace(go.Scatter(x=x, y=ep.get("pods"), mode="markers", marker=dict(color=RED, size=3, opacity=0.5),
                                 name="Number of VMs", showlegend=i == 0), row=r, col=c, secondary_y=True)
        fig.update_yaxes(title_text=ylab, row=r, col=c, secondary_y=False)
        fig.update_yaxes(title_text="Number of VMs", row=r, col=c, secondary_y=True, showgrid=False)
        fig.update_xaxes(title_text="Time", row=r, col=c)
    return _base(fig, height).update_layout(hovermode="closest")


def cumulative_reward(series, height=340):
    """Cumulative reward over time. series: [(name, rewards per tick, colour or None)]."""
    fig = go.Figure()
    for name, rw, colour in series:
        acc, s = [], 0.0
        for v in rw:
            s += v
            acc.append(s)
        fig.add_trace(go.Scatter(x=list(range(1, len(acc) + 1)), y=acc, mode="lines", name=name,
                                 line=dict(width=2, color=colour) if colour else dict(width=2)))
    fig.update_xaxes(title_text="Timestep")
    fig.update_yaxes(title_text="Cumulative reward")
    return _base(fig, height)


def total_bars(items, height=360, highlight=None):
    """Fig.7 (left) analogue: total reward per method. items: [(label, value, colour or None)]."""
    fig = go.Figure(go.Bar(x=[i[0] for i in items], y=[i[1] for i in items],
                           marker_color=[i[2] or (PURPLE if i[0] == highlight else GREY) for i in items],
                           text=[f"{i[1]:,.0f}" for i in items], textposition="outside"))
    fig.update_yaxes(title_text="Total Reward")
    fig.update_xaxes(tickangle=-25)
    return _base(fig, height).update_layout(hovermode="closest")


def gauge(value, title, ref=None, height=220):
    fig = go.Figure(go.Indicator(mode="gauge+number" + ("+delta" if ref is not None else ""), value=value,
                                 number={"suffix": "%"}, title={"text": title, "font": {"size": 14}},
                                 delta={"reference": ref} if ref is not None else None,
                                 gauge={"axis": {"range": [0, 100]}, "bar": {"color": PURPLE},
                                        "steps": [{"range": [0, 33], "color": "rgba(224,0,0,0.12)"},
                                                  {"range": [33, 66], "color": "rgba(242,160,0,0.15)"},
                                                  {"range": [66, 100], "color": "rgba(0,128,0,0.15)"}]}))
    return fig.update_layout(height=height, margin=dict(l=20, r=20, t=50, b=10), paper_bgcolor="rgba(0,0,0,0)")


def spark(values, total, height=90):
    """Tiny line of n_pass per record."""
    fig = go.Figure(go.Scatter(y=values, mode="lines+markers", line=dict(color=PURPLE, width=2)))
    fig.update_yaxes(range=[0, total], showticklabels=False)
    fig.update_xaxes(showticklabels=False)
    return fig.update_layout(height=height, margin=dict(l=5, r=5, t=5, b=5), paper_bgcolor="rgba(0,0,0,0)")


def history_line(labels, values, fc=None, height=200):
    """Per-cycle closeness sparkline; fc = forecast dict (pred, lo, hi) drawn as the next point with its band."""
    fig = go.Figure(go.Scatter(x=labels, y=values, mode="lines+markers+text", text=[f"{v:.0f}%" for v in values],
                               textposition="top center", line=dict(color=PURPLE, width=2), name="closeness"))
    if fc:
        fig.add_trace(go.Scatter(x=[labels[-1], "εκτίμηση"], y=[values[-1], fc["pred"]], mode="lines+markers",
                                 line=dict(color=GREY, dash="dash"), name="εκτίμηση",
                                 error_y=dict(type="data", symmetric=False, array=[0, fc["hi"] - fc["pred"]],
                                              arrayminus=[0, fc["pred"] - fc["lo"]])))
    fig.update_yaxes(range=[0, 100], title_text="%")
    return _base(fig, height).update_layout(showlegend=False, hovermode="closest")
