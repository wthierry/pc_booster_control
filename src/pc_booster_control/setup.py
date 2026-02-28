from setuptools import setup

package_name = "pc_booster_control"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    package_data={package_name: ["static/*"]},
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=[
        "setuptools",
        "fastapi",
        "uvicorn",
        "numpy",
        "opencv-python",
    ],
    zip_safe=True,
    maintainer="wthierry",
    maintainer_email="",
    description="ROS2 helper tools for Booster K1 RPC control",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "booster_web = pc_booster_control.web_server:main",
        ],
    },
)
