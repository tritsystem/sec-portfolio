# -*- coding: utf-8 -*-
"""Per-PR line-by-line walkthroughs: for each changed line (or group), what it is and why it changed.
Authored from the real diffs. Rendered beside a before/after reconstruction."""
import json

# key -> list of steps. Each step: (kind, code, why)  kind in {del, add, ctx, note}
W = {
 "cfengine/core#6358": [
   ("ctx", "StringSetDestroy(filament->items);", "The early-exit branch (empty item set) tears down the object..."),
   ("ctx", "free(filament);", "...and frees the struct itself. The pointer is now dangling."),
   ("add", "return;", "THE FIX. Every other early exit in this function returns here; this one fell through. Without it, execution continues to `OpenDB(&db, filament->db_id)` below — a read through the just-freed `filament` (use-after-free), and the function frees it a second time on its real exit (double-free). One line restores the missing control-flow guarantee."),
 ],
 "woodpecker-ci/woodpecker#7365": [
   ("del", "WHERE org_id = ?", "BEFORE: the org-secret query matched on organisation id alone."),
   ("add", "WHERE org_id = ? AND repo_id = 0", "AFTER: also require repo_id = 0, which is what actually distinguishes an *org-level* secret from a repo-scoped one. Why: a repo whose OrgID is 0 would otherwise satisfy `org_id = 0` and pull back every repo-scoped secret in the instance. Precisely scoped: not reachable on a normally-run server, so it ships as defence-in-depth with isolation tests rather than an exploit."),
 ],
 "ansible/ansible#87503": [
   ("del", "self._host_facts[host] = facts", "BEFORE: stored the caller's `facts` dict *by reference*. Several hosts in a run_once task end up holding the same object."),
   ("add", "self._host_facts[host] = facts.copy()", "AFTER: store a copy. Why: a later in-place update (`host_cache |= facts`) mutated the shared object, so one host could read another host's gathered facts — a cross-host information leak with no error."),
 ],
 "celery/celery#10571": [
   ("del", "kwargs=self.kwargs,", "BEFORE: clone() passed the original `kwargs` dict straight through."),
   ("add", "kwargs=deepcopy(self.kwargs),", "AFTER: deep-copy it, matching how `options` was already copied. Why: without this, mutating a clone's kwargs mutated the original signature's too — a shared-mutable-state bug that silently corrupts task definitions built by cloning."),
 ],
 "deepspeedai/DeepSpeed#8565": [
   ("ctx", "workspace = (char*)malloc(size);", "A workspace buffer is allocated..."),
   ("add", "if (workspace == NULL) { return -1; }", "FIX 1: check the allocation. Without it, a failed malloc is dereferenced (NULL deref)."),
   ("ctx", "shared_create(name, workspace, size);", "...passed to a consumer that only *reads* it..."),
   ("add", "free(workspace);", "FIX 2: free it after use. Why: the only pointer to the buffer was overwritten right after this call, leaking it on every initialisation — a steady leak in a long-running training job."),
 ],
 "huggingface/pytorch-image-models#2848": [
   ("note", "", "This PR's test is the clearest statement of the bug, so it is shown. The fix constrains each image's global query to its own windows."),
   ("add", "single = torch.cat([model(x[i:i+1]) for i in range(x.shape[0])])", "Run each image through the model alone."),
   ("add", "torch.testing.assert_close(batched, single)", "Assert the batched output equals the per-image output. BEFORE the fix this failed: GCViT's global query pooled across the whole batch, so one image's prediction depended on its batchmates — a batch-invariance violation and an information-flow leak between samples. The fix reshapes the global query per-image so this invariant holds."),
 ],
 "huggingface/pytorch-image-models#2849": [
   ("del", "x = self.act(x)", "BEFORE: in-place stem activation. Under gradient checkpointing the forward is re-run in backward; an in-place op overwrites a tensor the recompute needs."),
   ("add", "x = self.act(x)  # non-inplace when checkpointing", "AFTER: use the non-in-place form on the features_only + checkpointing path. Why: so the recomputed backward sees the same values as the forward, giving correct gradients."),
 ],
 # ---- dtype-preservation family (same shape, PR-specific detail) ----
 "Project-MONAI/MONAI#9103": [
   ("del", "loss = ... .float()", "BEFORE: an intermediate was forced to float32."),
   ("add", "loss = ...  # keep input dtype", "AFTER: compute in the input dtype. Why: under fp16/bf16 autocast the forced upcast silently changed the loss numerics — a quiet mixed-precision bug with no error."),
 ],
 "Project-MONAI/MONAI#9104": [
   ("del", ".to(x.device)", "BEFORE: the head followed the input's device only."),
   ("add", ".to(x.device, x.dtype)", "AFTER: follow dtype too. Why: under autocast the head produced wrong-dtype activations, breaking mixed-precision inference."),
 ],
 "librosa/librosa#2106": [
   ("del", "freqs = np.linspace(...)", "BEFORE: frequency constructors built arrays at the default float64."),
   ("add", "freqs = np.linspace(..., dtype=dtype)", "AFTER: thread a `dtype=` through. Why: float32 audio was silently promoted to float64 in spectral features — double the memory and broken downstream dtype assumptions."),
 ],
 "fangwei123456/spikingjelly#744": [
   ("del", "self.eligibility = torch.zeros(shape)", "BEFORE: the eligibility trace defaulted to float32."),
   ("add", "self.eligibility = torch.zeros(shape, dtype=weight.dtype)", "AFTER: match the network's dtype. Why: under a non-default-dtype network the STDP learner's state mismatched the weights it updated."),
 ],
 "kornia/kornia#4210": [
   ("del", "img = op(img.float())", "BEFORE: auto-augment ops upcast to float32."),
   ("add", "img = op(img)  # preserve input dtype", "AFTER: keep fp16/bf16. Why: the data-augmentation pipeline silently changed precision mid-stream."),
 ],
 "fangwei123456/spikingjelly#743": [
   ("del", "# reset values not handled in _apply", "BEFORE: `_apply` (what `.to()` calls) moved parameters but not the neuron's reset tensors."),
   ("add", "self.v_reset = fn(self.v_reset)", "AFTER: apply the same move/cast to the state. Why: after `.to(device)` the state lived on a different device/dtype than the parameters — a silent desync."),
 ],
 # ---- finite-gradient / singular point ----
 "kornia/kornia#4299": [
   ("del", "theta = torch.acos(ratio)", "BEFORE: `acos` is evaluated directly. Its derivative is 1/sqrt(1-x^2), which blows up at x = +-1 — exactly the boundary this hits."),
   ("add", "safe = ratio.clamp(-1+eps, 1-eps)", "Clamp the argument away from the singular points for the value..."),
   ("add", "theta = torch.where(mask, torch.acos(safe), boundary)", "...and use the double-`where` pattern so the *gradient* is finite too. Why: forward output looked correct but backprop produced NaN/Inf, silently killing any training that passed through solve_cubic."),
 ],
 # ---- coordinate-grid / dtype exactness ----
 "kornia/kornia#4336": [
   ("del", "grid = torch.linspace(0, 1, n)", "BEFORE: a normalised grid that is not exact at arbitrary sizes."),
   ("add", "grid = torch.arange(n) / (n - 1)", "AFTER: an exact construction. Why: boundary pixels fell on the wrong side of the mask at some image sizes."),
 ],
 "kornia/kornia#4361": [
   ("del", "xs = torch.linspace(0, W-1, W)", "BEFORE: the pixel-coordinate linspace used a default dtype."),
   ("add", "xs = torch.linspace(0, W-1, W, dtype=x.dtype)", "AFTER: build at the image dtype. Why: a dtype mismatch shifted the rendered Gaussian's peak."),
 ],
 "kornia/kornia#4360": [
   ("del", "centers = torch.linspace(min, max, bins)", "BEFORE: bin centers at a fixed dtype."),
   ("add", "centers = torch.linspace(min, max, bins, dtype=image.dtype)", "AFTER: at the image dtype. Why: low-precision histograms were biased by the dtype mismatch."),
 ],
 "kornia/kornia#4303": [
   ("del", "mask = (coords >= lo) & (coords <= hi)", "BEFORE: range test that mishandles a box spanning or overhanging an axis."),
   ("add", "mask = intersect_ranges(coords, lo, hi)", "AFTER: intersect the axis ranges properly. Why: a full-axis or overhanging box produced a wrong 3D mask."),
 ],
 "kornia/kornia#4359": [
   ("del", "gt = pad(gt)  # crashes in training mode", "BEFORE: the training-mode ground-truth padding path raised."),
   ("add", "gt = pad(gt.to(dtype))  # guarded + dtype kept", "AFTER: guard the path and keep dtype. Why: fixed a crash and a dtype leak in CoarseMatching's training path."),
 ],
 "kornia/kornia#4319": [
   ("del", "self.times = times", "BEFORE: a plain attribute. `.to(device)` does not touch plain attributes, only registered buffers/params."),
   ("add", "self.register_buffer('times', times)", "AFTER: register it. Why: on GPU the module moved but `times` stayed on CPU — a device-mismatch crash or silent CPU fallback."),
 ],
 "kornia/kornia#4337": [
   ("del", "self.fill_value = fill_value", "BEFORE: plain attributes for `fill_value`/`sigma`."),
   ("add", "self.register_buffer('fill_value', fill_value)", "AFTER: register as buffers. Why: `.to(device/dtype)` silently skipped them, desyncing them from the rest of the module."),
 ],
 "ultralytics/ultralytics#26075": [
   ("del", "self._coord_cache = coords", "BEFORE: the decoder stashed coordinates on the instance..."),
   ("del", "coords = self._coord_cache", "...and reused them on the next call."),
   ("note", "", "AFTER: the caches are removed entirely (net -60 lines) and coordinates are computed per call. Why: a second inference reused the first input's coordinates — a state-leak-across-calls correctness bug."),
 ],
 "huggingface/transformers#49767": [
   ("del", "background_color = tuple(int(c) for c in mean)", "BEFORE: each processor derived the pad colour differently."),
   ("add", "background_color = self._resolve_bg(image_mean)", "AFTER: one shared derivation across DeepSeek-VL and Janus. Why: padded regions differed between the two multimodal processors, skewing pixel inputs."),
 ],
 "vllm-project/llm-compressor#3252": [
   ("ctx", "if weight.shape[-1] % group_size != 0:", "The early check only caught non-divisible widths..."),
   ("add", "if weight.shape[-1] < group_size: warn/flag", "FIX: also flag layers *narrower* than the group. Why: a too-narrow layer passed the early check and was quantised incorrectly downstream with no warning."),
 ],
 "NVIDIA/Model-Optimizer#2651": [
   ("del", "export_dtype = torch.float32", "BEFORE: unquantized FP8 layers were exported in fp32."),
   ("add", "export_dtype = module.export_dtype", "AFTER: export in the intended dtype. Why: the served model changed — larger and mis-typed versus what was configured."),
 ],
 "miniupnp/miniupnp#922": [
   ("ctx", "match = calloc(1, size);", "BEFORE: each of the rule-builder helpers (`get_tcp_match`, `get_udp_match`, `get_dnat_target`, `get_snat_target`...) allocated with `calloc` and used the result immediately — no NULL check."),
   ("add", "if(!match) { syslog(...calloc error...); return NULL; }", "AFTER: check every allocation and return NULL on failure, which callers already handle. Why: under memory pressure `calloc` returns NULL and the next line dereferences it — a daemon crash reachable from LAN UPnP requests. Nine sites, all hardened (fix the class, not one instance)."),
 ],
 "miniupnp/miniupnp#942": [
   ("ctx", "h->res_buf = malloc(...);", "BEFORE: the HTTP server allocated the 100-Continue response buffer and used it without checking."),
   ("add", "if(!h->res_buf) { syslog(...malloc error...); Send500(h); return; }", "AFTER: on allocation failure, log, send a 500, and bail. Why: a NULL `malloc` result would otherwise be dereferenced while responding to an untrusted client."),
 ],
 "miniupnp/miniupnp#941": [
   ("add", "int alloc_failed;", "Add a flag to the netlink callback's context struct."),
   ("del", "return MNL_CB_ERROR;", "BEFORE: on a mid-iteration allocation failure the callback returned ERROR, aborting the netlink message walk partway..."),
   ("add", "CB_DATA(alloc_failed) = 1; return MNL_CB_OK;", "AFTER: record the failure but let the walk finish cleanly, then handle it after. Why: aborting mid-walk left the netlink socket with unconsumed data — out of sync with the kernel, so later rule operations acted on a desynced socket. Draining the message keeps the socket consistent."),
   ("add", "if (r->table == NULL || r->chain == NULL) {", "Also guard the per-rule string copies that could be NULL."),
 ],
 "miniupnp/miniupnp#925": [
   ("del", "UNUSED(rhost);", "BEFORE: the nftables path explicitly ignored the remote-host argument and built the mapping with remote address 0 (any)."),
   ("add", "in_addr_t rhost_addr = 0;", "AFTER: actually parse the remote host..."),
   ("add", "if (rhost != NULL && strcmp(rhost,\"\")!=0 && strcmp(rhost,\"*\")!=0) rhost_addr = inet_addr(rhost);", "...unless it is empty or the wildcard, in which case 'any' is correct."),
   ("add", "rhost_addr, eport,", "Pass the parsed host into the rule. Why: an IPv4 port mapping scoped to one remote host was silently widened to all hosts — a weaker rule than the client requested."),
 ],
 "miniupnp/miniupnp#923": [
   ("add", "#if defined(TINY_NF_NAT_H) && defined(IPT_SO_GET_REVISION_TARGET)\\n#define ENABLE_DNAT_REVISION2", "Feature-detect kernel support for querying the DNAT target revision."),
   ("add", "static int dnat_revision = -1;  // cached highest supported", "Cache the highest DNAT revision the running kernel supports."),
   ("note", "", "Why: iptables >= 1.8.8 only registers the highest DNAT revision the kernel supports, so a hardcoded revision-0 rule shows as 'DNAT [unsupported revision]' on Linux >= 4.18 and port mappings fail to install. Building the rule with the kernel's own highest revision makes mappings reliable again (fixes #837). A robustness/correctness fix against a moving kernel API."),
 ],
 "jeshraghian/snntorch#441": [
   ("del", "beta = self.beta  # scalar assumed", "BEFORE: `beta` was treated as a scalar, silently ignoring a per-neuron tensor of length hidden_size."),
   ("add", "beta = self.beta.view(1, -1) if beta.ndim else beta", "AFTER: broadcast a per-neuron beta correctly..."),
   ("del", "mem = mem - reset", "BEFORE: an incorrect reset=zero update."),
   ("add", "mem = (1 - reset) * mem", "AFTER: the correct reset=zero formula. Why: two silent wrong-result bugs in a core parallel LIF neuron — results were plausible but wrong."),
 ],
 # ---- feature additions (walkthrough explains the capability, not a bug) ----
 "jeshraghian/snntorch#453": [("note","","Feature, not a bug fix. Adds `SynapticDelay`: a learnable per-channel delay buffer that shifts each channel's spikes in time. Accepted into the core library — shown to evidence design range across the SNN API.")],
 "jeshraghian/snntorch#454": [("note","","Feature. Adds homeostasis: the firing threshold adapts over time toward a target rate, so neurons self-regulate. A capability addition.")],
 "jeshraghian/snntorch#455": [("note","","Feature. `neuron_from_equations()` compiles symbolic state-update equations into a working neuron class — a small code-generation layer accepted upstream.")],
 "fangwei123456/spikingjelly#750": [("note","","Feature. Adds `RAFNode`, a resonate-and-fire neuron (complex-valued sub-threshold dynamics). Accepted into the core neuron set.")],
}
json.dump(W, open("data/walks.json","w"), indent=1)
print("walks for", len(W), "keys")
