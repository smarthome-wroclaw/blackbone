import blackboneBlack from '../../../docs/assets/blackbone-black.svg';
import blackboneWhite from '../../../docs/assets/blackbone-white.svg';

const NavigationLogo = () => {
  return (
    <span className="blackbone-logo" role="img" aria-label="Blackbone">
      <img
        src={blackboneBlack}
        alt=""
        aria-hidden="true"
        className="blackbone-logo__image blackbone-logo__light h-5 w-auto xl:h-8"
      />
      <img
        src={blackboneWhite}
        alt=""
        aria-hidden="true"
        className="blackbone-logo__image blackbone-logo__dark h-5 w-auto xl:h-8"
      />
    </span>
  );
};

export default NavigationLogo;
