"""Build an int8 single Conv2D tflite (3x3, stride 1, SAME, 56x56x64 -> 56x56x64) for screening.

Run with the container's full TensorFlow: /opt/conf-env/bin/python host/make_conv_tflite.py OUT
"""
import sys, numpy as np, tensorflow as tf
H, W, CIN, COUT, K = 56, 56, 64, 64, 3
x_spec = tf.TensorSpec([1, H, W, CIN], tf.float32)
w = tf.constant(np.random.default_rng(1).uniform(-0.5, 0.5, (K, K, CIN, COUT)).astype(np.float32))
@tf.function(input_signature=[x_spec])
def f(x):
    return tf.nn.conv2d(x, w, strides=1, padding="SAME")
def rep():
    rng = np.random.default_rng(0)
    for _ in range(32):
        yield [rng.uniform(-1, 1, (1, H, W, CIN)).astype(np.float32)]
c = tf.lite.TFLiteConverter.from_concrete_functions([f.get_concrete_function()], f)
c.optimizations = [tf.lite.Optimize.DEFAULT]
c.representative_dataset = rep
c.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
c.inference_input_type = tf.int8
c.inference_output_type = tf.int8
open(sys.argv[1], "wb").write(c.convert())
