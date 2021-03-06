import os
import numpy as np
from skimage.feature import hog
from skimage.color import rgb2gray
from scipy.io import loadmat, savemat

from constants import BKG, FACE, HAIR


class Featurizer(object):
    def __init__(self, types=['loc', 'stats', 'hog'], window=0):
        self.fts = types
        self.window = window

    def types(self):
        return self.fts

    def get_patch_loc_feats(self, feats, x, y, sz):
        feats.append(float(x)/sz)
        feats.append(float(y)/sz)

    def get_patch_stats_features(self, feats, patch):
        # mean r g b
        feats.extend(np.mean(patch, axis=(0, 1)))
        # max r g b
        feats.extend(np.max(patch, axis=(0, 1)))
        # min r g b
        feats.extend(np.min(patch, axis=(0, 1)))

    def get_hog_features(self, feats, patch):
        m, n, _ = patch.shape
        gr_patch = rgb2gray(patch) if patch.ndim == 3 else patch
        # hog
        feats.extend(hog(
            gr_patch, orientations=32, pixels_per_cell=(m, n),
            cells_per_block=(1, 1), block_norm='L2-Hys'))

    def get_color_features(self, feats, patch):
        feats.extend(patch.ravel())

    def get_keyp_polar_features(self, feats, x, y, sz, keyps):
        xy = np.array([x, y], dtype=np.float)
        kps = np.asarray([
            keyps[keyps[:, 0].argmax(), :],
            keyps[keyps[:, 0].argmin(), :],
            keyps[keyps[:, 1].argmax(), :],
            keyps[keyps[:, 1].argmin(), :],
            keyps.mean(axis=0),
        ])
        diffs = (kps - xy) / sz
        feats.extend((diffs*diffs).sum(axis=1).ravel())
        feats.extend(np.arctan2(diffs[:, 1], diffs[:, 0]).ravel())

    def get_keyp_color_features(self, feats, im, keyps):
        for i in range(keyps.shape[0]):
            feats.extend(self._sample_patch(im, keyps[i, 0], keyps[i, 1]))

    def get_keyp_mean_color_features(self, feats, im, keyps):
        for ft in self._sample_keyp_mean_patches(im, keyps):
            feats.extend(ft)

    def get_keyp_mean_cdiff_features(self, feats, patch, im, keyps):
        p = patch.astype(np.int16).ravel()
        for k in self._sample_keyp_mean_patches(im, keyps):
            feats.extend(k.astype(np.int16) - p)

    def get_chist_diff_features(self, feats, patch, im, keyps):
        p = self._chist_feats(patch)
        for k in self._sample_keyp_mean_patches(im, keyps):
            feats.extend(self._chist_feats(k.reshape(patch.shape)) - p)

    def get_chist_features(self, feats, patch):
        feats.extend(self._chist_feats(patch))

    def get_heirarchical_labels(self, feats, x, y, hr_maps):
        for pr in hr_maps:
            p = pr[x:x+self.window, y:y+self.window]
            feats.extend(self._hr_label_feats(p))

    def get_neighb_hr_labels(self, feats, x, y, hr_maps):
        pass

    def get_lbp_features(self, feats, patch):
        pass

    def get_glcm_features(self, feats, patch):
        pass

    def _hr_label_feats(self, p):
        s = self.window ** 2 * 1.0
        return [np.sum(p==BKG)/s, np.sum(p==FACE)/s, np.sum(p==FACE)/s]

    def _chist_feats(self, patch):
        dim = patch.ndim
        if dim == 3:
            p = patch.reshape((-1, 3))
            h, e = np.histogramdd(p, bins=(8, 8, 8), normed=True)
            h = h.ravel()
        else:
            h, e = np.histogram(patch, bins=16, normed=True)
        return h

    def _sample_keyp_mean_patches(self, im, keyps):
        fts = []
        meank = np.mean(keyps, axis=0)
        fts.append(self._sample_patch(im, meank[0], meank[1]))
        maxkx = keyps[keyps[:, 0].argmax(), :]
        fts.append(self._sample_patch(im,
                                      (meank[0] + maxkx[0]) // 2,
                                      (meank[1] + maxkx[1]) // 2))
        minkx = keyps[keyps[:, 0].argmin(), :]
        fts.append(self._sample_patch(im,
                                      (meank[0] + minkx[0]) // 2,
                                      (meank[1] + minkx[1]) // 2))
        return fts

    def _sample_patch(self, im, x, y):
        xs, ys = int(max(x - self.window // 2, 0)), int(max(y - self.window // 2, 0))
        p = im[xs:xs+self.window, ys:ys+self.window, :]
        if self.window != p.shape[0]:
            p = np.lib.pad(p, ((0, self.window - p.shape[0]), (0, 0), (0, 0)),
                           'constant')
        if self.window != p.shape[1]:
            p = np.lib.pad(p, ((0, 0), (0, self.window - p.shape[1]), (0, 0)),
                           'constant')
        return p.ravel()
#        return p / 255. if p.dtype == np.uint8 else p

    def _norm_face_dims(self, keyps):
        return float(np.max(keyps[:, 1]) - np.min(keyps[:, 1]))

    def process(self, x, y, patch, im, keypoints, hr_maps=[]):
        keypoints = keypoints[:-1, :]  # ignore the m, n appended to keypoint list
        norm = self._norm_face_dims(keypoints)
        ft = []
        for t in self.fts:
            if t == 'loc': self.get_patch_loc_feats(ft, x, y, norm)
            elif t == 'stats': self.get_patch_stats_features(ft, patch)
            elif t == 'hog': self.get_hog_features(ft, patch)
            elif t == 'col': self.get_color_features(ft, patch)
            elif t == 'chist': self.get_chist_features(ft, patch)
            elif t == 'histdiff': self.get_chist_diff_features(ft, patch, im, keypoints)
            elif t == 'kcol': self.get_keyp_color_features(ft, im, keypoints)
            elif t == 'kmeancol': self.get_keyp_mean_color_features(ft, im, keypoints)
            elif t == 'kmeandiff':
                self.get_keyp_mean_cdiff_features(ft, patch, im, keypoints)
            elif t == 'kpolar':
                self.get_keyp_polar_features(ft, x, y, norm, keypoints)
        if hr_maps: self.get_heirarchical_labels(ft, x, y, hr_maps)
        return ft

    def processY(self, gtpatch):
        # if np.count_nonzero(gtpatch == HAIR) > 0.8 * np.size(gtpatch):
        #     return HAIR
        return np.bincount(gtpatch.ravel()).argmax()
