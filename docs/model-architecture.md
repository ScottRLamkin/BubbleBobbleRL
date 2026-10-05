# Model architecture

The model is the `Agent` class in `scripts/train_ppo.py`: a shared encoder
feeding two linear heads (actor-critic). The trained model uses the MLP
encoder. About 226,000 parameters in total.

## Current model (state observation)

```mermaid
flowchart TB
    In["state observation<br/>616 floats"]
    subgraph Encoder["shared encoder"]
        L1["Linear 616 -> 256<br/>157,952 params"]
        T1["Tanh"]
        L2["Linear 256 -> 256<br/>65,792 params"]
        T2["Tanh"]
        L1 --> T1 --> L2 --> T2
    end
    In --> L1
    T2 --> Actor["Actor head<br/>Linear 256 -> 9<br/>2,313 params"]
    T2 --> Critic["Critic head<br/>Linear 256 -> 1<br/>257 params"]
    Actor --> Dist["Categorical over 9 actions<br/>(sampled, also at playback)"]
    Critic --> V["state value V(s)"]
```

- Weights use orthogonal initialisation (gain sqrt(2) in the encoder, 0.01 on
  the actor, 1.0 on the critic).
- The actor and critic share the whole encoder; only the last layer differs.
- There is no memory (no recurrence, no frame stacking). Each decision uses
  the current observation only.
- Actions are sampled from the distribution during playback too, so the same
  model gives different episodes.

## How a PPO update flows

```mermaid
flowchart TB
    Roll["Collect rollout<br/>16 envs x 128 steps = 2,048 samples<br/>store obs, action, log-prob, reward, done, value"]
    GAE["Compute advantages (GAE, gamma 0.99, lambda 0.95)<br/>returns = advantages + values"]
    MB["Shuffle, split into 4 minibatches of 512"]
    Loss["loss = clipped policy loss<br/>+ 0.5 x value MSE<br/>- 0.01 x entropy"]
    Step["Adam step, lr 2.5e-4<br/>gradient norm clipped to 0.5"]
    Save["save model.pt, log to TensorBoard"]
    Roll --> GAE --> MB --> Loss --> Step
    Step -- "4 epochs over the same rollout" --> MB
    Step --> Save
    Save -- "until 2M steps" --> Roll
```

## Pixel variant (`--obs screen`, not yet working)

The script also defines a CNN encoder for the 64x96 1-bit screen. It has never
been trained, and it currently crashes on the first forward pass: the flatten
size is written as `32 * 7 * 11` (2,464) but the convolutions actually produce
`32 * 6 * 10` (1,920).

```mermaid
flowchart TB
    Img["screen observation<br/>64 x 96, 1 bit, single frame"]
    C1["Conv 1 -> 16, 8x8, stride 4<br/>output 16 x 15 x 23"]
    C2["Conv 16 -> 32, 4x4, stride 2<br/>output 32 x 6 x 10"]
    F["Flatten: 1,920"]
    FC["Linear -> 256<br/>(code expects 2,464 inputs: bug)"]
    Heads["same actor and critic heads"]
    Img --> C1 -- ReLU --> C2 -- ReLU --> F --> FC -- ReLU --> Heads
```

A single frame also hides motion (jump phase, which way a bubble is drifting),
so a working pixel setup would want frame stacking on top of the size fix.
