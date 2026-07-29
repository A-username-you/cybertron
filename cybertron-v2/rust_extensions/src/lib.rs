use pyo3::prelude::*;

#[pyfunction]
fn calculate_entropy(data: &[u8]) -> PyResult<f64> {
    if data.is_empty() {
        return Ok(0.0);
    }
    let mut counts = [0u64; 256];
    for &byte in data {
        counts[byte as usize] += 1;
    }
    let len = data.len() as f64;
    let entropy: f64 = counts.iter()
        .filter(|&&c| c > 0)
        .map(|&count| {
            let p = count as f64 / len;
            -p * p.log2()
        })
        .sum();
    Ok(entropy)
}

#[pymodule]
fn cybertron_rs(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(calculate_entropy, m)?)?;
    Ok(())
}
