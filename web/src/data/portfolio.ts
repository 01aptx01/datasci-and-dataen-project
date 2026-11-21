export type CovarianceMatrix3 = [[number, number, number], [number, number, number], [number, number, number]];
export type PortfolioWeights = [number, number, number];

const tolerance = 1e-10;

export function minimumEigenvalueSymmetric3(matrix: number[][]): number {
  if (matrix.length !== 3 || matrix.some((row) => row.length !== 3)) throw new Error("Matrix must be 3 by 3");
  if (matrix.some((row) => row.some((value) => !Number.isFinite(value)))) throw new Error("Matrix values must be finite");
  for (let row = 0; row < 3; row += 1) {
    for (let column = row + 1; column < 3; column += 1) {
      if (Math.abs(matrix[row][column] - matrix[column][row]) > 1e-12) throw new Error("Matrix must be symmetric");
    }
  }

  const [a, b, c] = [matrix[0][0], matrix[1][1], matrix[2][2]];
  const [d, e, f] = [matrix[0][1], matrix[0][2], matrix[1][2]];
  const mean = (a + b + c) / 3;
  const spreadSquared = ((a - mean) ** 2 + (b - mean) ** 2 + (c - mean) ** 2 + 2 * (d ** 2 + e ** 2 + f ** 2)) / 6;
  if (spreadSquared <= Number.EPSILON) return mean;

  const spread = Math.sqrt(spreadSquared);
  const normalized = [
    [(a - mean) / spread, d / spread, e / spread],
    [d / spread, (b - mean) / spread, f / spread],
    [e / spread, f / spread, (c - mean) / spread],
  ];
  const determinant = normalized[0][0] * (normalized[1][1] * normalized[2][2] - normalized[1][2] * normalized[2][1])
    - normalized[0][1] * (normalized[1][0] * normalized[2][2] - normalized[1][2] * normalized[2][0])
    + normalized[0][2] * (normalized[1][0] * normalized[2][1] - normalized[1][1] * normalized[2][0]);
  const angle = Math.acos(Math.max(-1, Math.min(1, determinant / 2))) / 3;
  const largest = mean + 2 * spread * Math.cos(angle);
  const smallest = mean + 2 * spread * Math.cos(angle + (2 * Math.PI / 3));
  const middle = 3 * mean - largest - smallest;
  return Math.min(largest, middle, smallest);
}

export function computePortfolioVolatility(covariance: number[][], weights: number[]): number {
  if (weights.length !== 3) throw new Error("Portfolio weights must contain exactly three values");
  if (weights.some((weight) => !Number.isFinite(weight))) throw new Error("Portfolio weights must be finite");
  if (weights.some((weight) => weight < 0)) throw new Error("Portfolio weights must be nonnegative");
  if (Math.abs(weights.reduce((sum, weight) => sum + weight, 0) - 1) > tolerance) throw new Error("Portfolio weights must sum to 1");
  if (covariance.length !== 3 || covariance.some((row) => row.length !== 3)) throw new Error("Covariance matrix must be 3 by 3");
  if (covariance.some((row) => row.some((value) => !Number.isFinite(value)))) throw new Error("Covariance matrix values must be finite");
  const scale = Math.max(1, ...covariance.flat().map(Math.abs));
  const matrixTolerance = tolerance * scale;
  for (let row = 0; row < 3; row += 1) {
    if (covariance[row][row] < -matrixTolerance) throw new Error("Covariance matrix must be positive semidefinite");
    for (let column = row + 1; column < 3; column += 1) {
      if (Math.abs(covariance[row][column] - covariance[column][row]) > matrixTolerance) throw new Error("Covariance matrix must be symmetric");
    }
  }
  const [a, b, c] = [covariance[0][0], covariance[1][1], covariance[2][2]];
  const [d, e, f] = [covariance[0][1], covariance[0][2], covariance[1][2]];
  const minors = [a * b - d * d, a * c - e * e, b * c - f * f];
  const determinant = a * (b * c - f * f) - d * (d * c - e * f) + e * (d * f - b * e);
  const psdTolerance = tolerance * Math.max(1, scale ** 3);
  if (minors.some((minor) => minor < -psdTolerance) || determinant < -psdTolerance) throw new Error("Covariance matrix must be positive semidefinite");
  const variance = weights.reduce((outer, weight, row) => outer + weight * weights.reduce((inner, other, column) => inner + other * covariance[row][column], 0), 0);
  if (!Number.isFinite(variance) || variance < -psdTolerance) throw new Error("Portfolio variance is invalid for the selected weights");
  return Math.sqrt(Math.max(0, variance));
}

export function correlationFromCovariance(covariance: number[][], first: number, second: number): number | null {
  if (first === second || covariance.length !== 3 || covariance.some((row) => row.length !== 3)) return null;
  const varianceFirst = covariance[first]?.[first];
  const varianceSecond = covariance[second]?.[second];
  const covariancePair = covariance[first]?.[second];
  if (![varianceFirst, varianceSecond, covariancePair].every((value) => typeof value === "number" && Number.isFinite(value)) || varianceFirst! <= 0 || varianceSecond! <= 0) return null;
  const result = covariancePair! / Math.sqrt(varianceFirst! * varianceSecond!);
  return Number.isFinite(result) ? result : null;
}
