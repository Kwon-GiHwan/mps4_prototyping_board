"""Build an int8 BATCH_MATMUL tflite (x @ x^T) for the U85 tensor-core probe.

Run with the container's full TensorFlow: /opt/conf-env/bin/python host/make_matmul_tflite.py OUT
"""
import sys, numpy as np, tensorflow as tf
B, M, K = 1, 64, 256
x_spec = tf.TensorSpec([B, M, K], tf.float32)
@tf.function(input_signature=[x_spec])
def f(x):
    return tf.linalg.matmul(x, x, transpose_b=True)
def rep():
    rng = np.random.default_rng(0)
    for _ in range(32):
        yield [rng.uniform(-1, 1, (B, M, K)).astype(np.float32)]
c = tf.lite.TFLiteConverter.from_concrete_functions([f.get_concrete_function()], f)
c.optimizations = [tf.lite.Optimize.DEFAULT]
c.representative_dataset = rep
c.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
c.inference_input_type = tf.int8
c.inference_output_type = tf.int8
open(sys.argv[1], "wb").write(c.convert())
