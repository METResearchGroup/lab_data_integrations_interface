import styles from "./ProgressBar.module.css";

export default function ProgressBar() {
	return (
		<div className={styles.track}>
			<div className={styles.bar} />
		</div>
	);
}
