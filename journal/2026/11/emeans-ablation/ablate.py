"""Ablate e-means using the authors' own NumpyEmeans (faiss/contrib/e_means).
Arms differ only by switching components off; Lloyd = faiss.Kmeans, same init.
Metric: held-out test MSE / Lloyd@25 test MSE.

Setup: copy e_means.py and base.py from facebookresearch/faiss contrib/e_means
(commit fc1095a9314f) into ./emeans/ with an empty __init__.py; download
sift-128-euclidean.hdf5 and glove-100-angular.hdf5 from ann-benchmarks.com as
sift.hdf5 / glove.hdf5. Run: python3 ablate.py sift 1000000 1024 1,2,3
Tested with faiss-cpu 1.15.1, scikit-learn 1.9.1, numpy 2.4.6."""
import sys, json, time, numpy as np, h5py, faiss
from emeans.e_means import NumpyEmeans

class MacQueen(NumpyEmeans):      # cumulative S+=s, N+=n (no forgetting)
    def update(self, stats):
        self._require_running()
        expected_n = min(self.recipe["batch_size"], self.recipe["epoch_rows"][self._epoch] - self._epoch_rows)
        ids, sums, counts, obj = self._prepare_statistics(stats, expected_n)
        self._apply_statistics(ids, sums, counts, obj, 1.0, 1.0, False)
        self._finish_step(expected_n)

class ConstAlpha(NumpyEmeans):    # EMA without cosine annealing
    def update(self, stats):
        self._require_running()
        expected_n = min(self.recipe["batch_size"], self.recipe["epoch_rows"][self._epoch] - self._epoch_rows)
        ids, sums, counts, obj = self._prepare_statistics(stats, expected_n)
        a = self.recipe["alpha0"]
        self._apply_statistics(ids, sums, counts, obj, a, 1.0 - a, a == 1)
        self._finish_step(expected_n)

def nofinal(cls):                 # return the running centroids, skip closing means
    class C(cls):
        def finalize(self):
            c = self._centroids.copy(); super().finalize(); self.centroids = c; return c
    return C

def mse(x, c):
    idx = faiss.IndexFlatL2(c.shape[1]); idx.add(np.ascontiguousarray(c, dtype="float32"))
    D, _ = idx.search(x, 1); return float(D.mean())

def main(ds, n, k, seeds):
    h = h5py.File(f"{ds}.hdf5")
    xall = np.ascontiguousarray(h["train"][:n], dtype="float32"); xt = np.ascontiguousarray(h["test"][:], dtype="float32")
    d = xall.shape[1]; out = []
    for seed in seeds:
        init = xall[np.random.RandomState(seed).permutation(n)[:k]].copy()
        def rec(arm, T, c, secs, extra=None):
            r = dict(ds=ds, n=n, k=k, seed=seed, arm=arm, T=T, test=mse(xt, c), secs=round(secs, 2)); r.update(extra or {})
            out.append(r); print(json.dumps(r), flush=True)
        for T in [1, 2, 3, 5, 10, 25]:
            t = time.time(); km = faiss.Kmeans(d, k, niter=T, seed=seed, max_points_per_centroid=10**9)
            km.train(xall, init_centroids=init); rec("lloyd", T, km.centroids, time.time() - t)
        arms = {"emeans": (NumpyEmeans, {}), "no_revival": (NumpyEmeans, {"unused_threshold": 0.0}),
                "no_finalize": (nofinal(NumpyEmeans), {}), "const_alpha": (ConstAlpha, {}),
                "macqueen": (MacQueen, {}), "macqueen_bare": (nofinal(MacQueen), {"unused_threshold": 0.0})}
        for arm, (cls, kw) in arms.items():
            for T in ([1, 1.5, 2, 3, 5] if arm == "emeans" else [2, 3]):
                t = time.time(); em = cls(d, k, nepochs=T, seed=seed, capture_assignments=False, **kw)
                c, _ = em.train(xall, init_centroids=init)
                rec(arm, T, c, time.time() - t, dict(B=em.recipe["batch_size"], alpha0=round(em.recipe["alpha0"], 4), splits=em.n_splits))
        from sklearn.cluster import MiniBatchKMeans
        for T in [2, 3, 5]:
            t = time.time(); mb = MiniBatchKMeans(k, init=init, n_init=1, max_iter=T, batch_size=1024, random_state=seed,
                                                  max_no_improvement=None, tol=0.0).fit(xall)
            rec("sklearn_mbk", T, mb.cluster_centers_.astype("float32"), time.time() - t)
    return out

if __name__ == "__main__":
    ds, n, k = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]); seeds = [int(s) for s in sys.argv[4].split(",")]
    res = main(ds, n, k, seeds)
    json.dump(res, open(f"res_{ds}_{n}_{k}.json", "w"))
